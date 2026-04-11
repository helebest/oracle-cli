"""OCI API helpers using the Oracle Cloud Infrastructure Python SDK."""

from typing import Any

import oci

from .config import load_config

PROTO_MAP = {"6": "TCP", "17": "UDP", "1": "ICMP", "all": "ALL"}


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
