"""OCI API helpers using the Oracle Cloud Infrastructure Python SDK."""

from datetime import datetime, timedelta, timezone
from typing import Any

import oci

from .config import load_config

PROTO_MAP = {"6": "TCP", "17": "UDP", "1": "ICMP", "all": "ALL"}

METRICS_NAMESPACE = "oci_computeagent"

# (metric_id, display_label, row_format). Byte counters use .rate() (bytes/sec)
# because raw OCI values are cumulative; others use .mean() on the bucket.
METRICS_SPEC = [
    ("CpuUtilization", "CPU %", "{:6.1f}"),
    ("MemoryUtilization", "Mem %", "{:6.1f}"),
    ("LoadAverage", "Load", "{:6.2f}"),
    ("NetworksBytesIn", "NetIn MB/min", "{:6.1f}"),
    ("NetworksBytesOut", "NetOut MB/min", "{:6.1f}"),
    ("DiskBytesRead", "DiskR MB/min", "{:6.1f}"),
    ("DiskBytesWritten", "DiskW MB/min", "{:6.1f}"),
]

_BYTES_METRICS = {"NetworksBytesIn", "NetworksBytesOut", "DiskBytesRead", "DiskBytesWritten"}


def _get_oci_config() -> dict:
    """Load OCI SDK config from ~/.oci/config."""
    return oci.config.from_file()


def _get_ids() -> tuple[str, str]:
    """Return (instance_id, compartment_id) from config.yaml."""
    cfg = load_config()["oci"]
    return cfg["instance_id"], cfg["compartment_id"]


def get_instance_details() -> dict[str, Any]:
    """Fetch instance details from OCI API."""
    config = _get_oci_config()
    compute = oci.core.ComputeClient(config)
    instance_id, _ = _get_ids()

    inst = compute.get_instance(instance_id).data
    sc = inst.shape_config

    return {
        "display_name": inst.display_name,
        "lifecycle_state": inst.lifecycle_state,
        "shape": inst.shape,
        "ocpus": sc.ocpus if sc else None,
        "memory_gb": sc.memory_in_gbs if sc else None,
        "bandwidth_gbps": sc.networking_bandwidth_in_gbps if sc else None,
        "availability_domain": inst.availability_domain,
        "fault_domain": inst.fault_domain,
        "time_created": inst.time_created,
    }


def instance_action(action: str) -> str:
    """Perform instance lifecycle action (START/STOP/SOFTSTOP/SOFTRESET/RESET)."""
    config = _get_oci_config()
    compute = oci.core.ComputeClient(config)
    instance_id, _ = _get_ids()

    resp = compute.instance_action(instance_id, action)
    return resp.data.lifecycle_state


def get_public_ip() -> str | None:
    """Get the instance's primary public IP address."""
    config = _get_oci_config()
    compute = oci.core.ComputeClient(config)
    vn_client = oci.core.VirtualNetworkClient(config)
    instance_id, compartment_id = _get_ids()

    vnic_attachments = compute.list_vnic_attachments(
        compartment_id, instance_id=instance_id
    ).data

    for va in vnic_attachments:
        if va.lifecycle_state == "ATTACHED":
            vnic = vn_client.get_vnic(va.vnic_id).data
            if vnic.public_ip:
                return vnic.public_ip
    return None


def get_network_info() -> dict[str, Any]:
    """Get VCN, subnet, and IP information."""
    config = _get_oci_config()
    compute = oci.core.ComputeClient(config)
    vn_client = oci.core.VirtualNetworkClient(config)
    instance_id, compartment_id = _get_ids()

    vnic_attachments = compute.list_vnic_attachments(
        compartment_id, instance_id=instance_id
    ).data

    for va in vnic_attachments:
        if va.lifecycle_state != "ATTACHED":
            continue
        vnic = vn_client.get_vnic(va.vnic_id).data
        subnet = vn_client.get_subnet(va.subnet_id).data
        vcn = vn_client.get_vcn(subnet.vcn_id).data

        return {
            "vcn_name": vcn.display_name,
            "vcn_cidr": vcn.cidr_block,
            "subnet_name": subnet.display_name,
            "subnet_cidr": subnet.cidr_block,
            "public_ip": vnic.public_ip,
            "private_ip": vnic.private_ip,
        }
    return {}


def add_ingress_rule(protocol: str, port: int, description: str = "") -> None:
    """Add an ingress rule to the security list attached to the instance's subnet."""
    config = _get_oci_config()
    compute = oci.core.ComputeClient(config)
    vn_client = oci.core.VirtualNetworkClient(config)
    instance_id, compartment_id = _get_ids()

    vnic_attachments = compute.list_vnic_attachments(
        compartment_id, instance_id=instance_id
    ).data

    for va in vnic_attachments:
        if va.lifecycle_state != "ATTACHED":
            continue
        subnet = vn_client.get_subnet(va.subnet_id).data
        sl_id = subnet.security_list_ids[0]
        sl = vn_client.get_security_list(sl_id).data

        proto_num = {"TCP": "6", "UDP": "17"}[protocol.upper()]
        port_range = oci.core.models.PortRange(min=port, max=port)

        if proto_num == "6":
            options_kwargs = {"tcp_options": oci.core.models.TcpOptions(destination_port_range=port_range)}
        else:
            options_kwargs = {"udp_options": oci.core.models.UdpOptions(destination_port_range=port_range)}

        new_rule = oci.core.models.IngressSecurityRule(
            source="0.0.0.0/0",
            source_type="CIDR_BLOCK",
            protocol=proto_num,
            description=description,
            **options_kwargs,
        )

        existing_rules = list(sl.ingress_security_rules)
        existing_rules.append(new_rule)

        vn_client.update_security_list(
            sl_id,
            oci.core.models.UpdateSecurityListDetails(
                ingress_security_rules=existing_rules,
            ),
        )
        return
    raise RuntimeError("No attached VNIC found")


def get_metrics(hours: int = 24) -> list[dict[str, Any]]:
    """Query VM load metrics from OCI Monitoring for the past ``hours``.

    Returns one dict per metric in METRICS_SPEC with keys: name, label, fmt,
    is_bytes, min, avg, max, total_gb (bytes only), values (list of floats in
    display units), points (count).
    """
    config = _get_oci_config()
    client = oci.monitoring.MonitoringClient(config)
    instance_id, compartment_id = _get_ids()

    # Hour-level buckets for long windows, 5-minute for short, to keep the
    # series between ~12 and ~168 points.
    interval_minutes = 60 if hours >= 24 else 5
    interval = f"{interval_minutes}m"

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    results = []
    for metric, label, fmt in METRICS_SPEC:
        is_bytes = metric in _BYTES_METRICS
        aggregator = "rate()" if is_bytes else "mean()"
        query = f'{metric}[{interval}]{{resourceId = "{instance_id}"}}.{aggregator}'
        details = oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace=METRICS_NAMESPACE,
            query=query,
            start_time=start,
            end_time=end,
        )
        try:
            resp = client.summarize_metrics_data(compartment_id, details).data
        except oci.exceptions.ServiceError as e:
            results.append({
                "name": metric, "label": label, "fmt": fmt, "is_bytes": is_bytes,
                "error": f"{e.status} {e.code}",
                "values": [], "points": 0,
                "min": None, "avg": None, "max": None, "total_gb": None,
            })
            continue

        raw = [p.value for p in resp[0].aggregated_datapoints] if resp else []
        clean = [v for v in raw if v is not None]

        total_gb = None
        if is_bytes:
            # .rate() returns bytes/sec; convert to MB/min and integrate to GB.
            total_gb = sum(clean) * interval_minutes * 60 / 1024 / 1024 / 1024
            values = [v * 60 / 1024 / 1024 for v in clean]
        else:
            values = clean

        summary = {
            "name": metric, "label": label, "fmt": fmt, "is_bytes": is_bytes,
            "values": values, "points": len(values),
            "min": min(values) if values else None,
            "avg": sum(values) / len(values) if values else None,
            "max": max(values) if values else None,
            "total_gb": total_gb,
            "window_start": start,
            "window_end": end,
            "interval": interval,
        }
        results.append(summary)
    return results


def get_security_rules() -> list[dict[str, str]]:
    """Get ingress rules from security lists attached to the instance's subnet."""
    config = _get_oci_config()
    compute = oci.core.ComputeClient(config)
    vn_client = oci.core.VirtualNetworkClient(config)
    instance_id, compartment_id = _get_ids()

    vnic_attachments = compute.list_vnic_attachments(
        compartment_id, instance_id=instance_id
    ).data

    rules = []
    for va in vnic_attachments:
        if va.lifecycle_state != "ATTACHED":
            continue
        subnet = vn_client.get_subnet(va.subnet_id).data

        for sl_id in subnet.security_list_ids:
            sl = vn_client.get_security_list(sl_id).data
            for rule in sl.ingress_security_rules:
                proto = PROTO_MAP.get(rule.protocol, rule.protocol)
                port_range = ""
                if rule.tcp_options and rule.tcp_options.destination_port_range:
                    pr = rule.tcp_options.destination_port_range
                    port_range = str(pr.min) if pr.min == pr.max else f"{pr.min}-{pr.max}"
                elif rule.udp_options and rule.udp_options.destination_port_range:
                    pr = rule.udp_options.destination_port_range
                    port_range = str(pr.min) if pr.min == pr.max else f"{pr.min}-{pr.max}"

                rules.append({
                    "source": rule.source,
                    "protocol": proto,
                    "port_range": port_range,
                    "description": rule.description or "",
                })
        break
    return rules
