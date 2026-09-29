#!/usr/bin/env bash
# Cloud migration Step 2 — provisions the Azure B2ms VM for Kafka + Debezium (§37).
# Idempotent-ish: uses `az ... create`, which for most of these resource types no-ops/updates
# in place if the resource already exists under the same name. Safe to re-run.
#
# Run from the repo root: bash azure/provision_vm.sh

set -euo pipefail

RESOURCE_GROUP="ekadai-rg"
LOCATION="southeastasia"
VNET_NAME="ekadai-vnet"
SUBNET_NAME="ekadai-subnet"
NSG_NAME="ekadai-nsg"
PIP_V4_NAME="ekadai-vm-pip-v4"
PIP_V6_NAME="ekadai-vm-pip-v6"
NIC_NAME="ekadai-vm-nic"
IP_CONFIG_V4="ipconfig-v4"
IP_CONFIG_V6="ipconfig-v6"
VM_NAME="ekadai-vm"
VM_SIZE="Standard_B2ms"
SSH_KEY_PATH="$HOME/.ssh/ekadai_azure_vm.pub"
ADMIN_USER="ekadai"

MY_IP="$(curl -s https://api.ipify.org)"
echo "Scoping SSH access to current public IP: ${MY_IP}"
echo "(If your IP changes later, update the NSG rule — see the printed az command at the end.)"

echo "--- Resource group ---"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output table

echo "--- Dual-stack VNet (IPv4 + IPv6 address space) ---"
az network vnet create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VNET_NAME" \
  --address-prefixes 10.0.0.0/16 "ace:cab:deca::/48" \
  --subnet-name "$SUBNET_NAME" \
  --subnet-prefixes 10.0.1.0/24 "ace:cab:deca:deed::/64" \
  --output table

echo "--- NSG: SSH from this machine only, Kafka/Connect/Schema-Registry ports ---"
az network nsg create --resource-group "$RESOURCE_GROUP" --name "$NSG_NAME" --output table

az network nsg rule create \
  --resource-group "$RESOURCE_GROUP" --nsg-name "$NSG_NAME" \
  --name allow-ssh --priority 100 --access Allow --protocol Tcp \
  --direction Inbound --source-address-prefixes "${MY_IP}/32" --source-port-ranges '*' \
  --destination-port-ranges 22 --output table

# Kafka (9092 internal/PLAINTEXT + 9093 controller stay internal to the VM's own Docker
# network — not opened here), Schema Registry (8081), Kafka Connect REST (8083): scoped to the
# VNet's own address ranges for now (Databricks' VNet isn't provisioned yet — see plan's
# "explicitly not done" note; this will be narrowed to Databricks' actual range once it exists).
az network nsg rule create \
  --resource-group "$RESOURCE_GROUP" --nsg-name "$NSG_NAME" \
  --name allow-kafka-broker --priority 110 --access Allow --protocol Tcp \
  --direction Inbound --source-address-prefixes "${MY_IP}/32" --source-port-ranges '*' \
  --destination-port-ranges 29092 8081 8083 5432 --output table

echo "--- Public IPs (IPv4 + IPv6, Standard SKU) ---"
az network public-ip create \
  --resource-group "$RESOURCE_GROUP" --name "$PIP_V4_NAME" \
  --sku Standard --version IPv4 --allocation-method Static --output table

az network public-ip create \
  --resource-group "$RESOURCE_GROUP" --name "$PIP_V6_NAME" \
  --sku Standard --version IPv6 --allocation-method Static --output table

echo "--- NIC with both IPv4 and IPv6 configs ---"
az network nic create \
  --resource-group "$RESOURCE_GROUP" --name "$NIC_NAME" \
  --vnet-name "$VNET_NAME" --subnet "$SUBNET_NAME" \
  --network-security-group "$NSG_NAME" \
  --ip-forwarding false \
  --private-ip-address-version IPv4 \
  --public-ip-address "$PIP_V4_NAME" \
  --output table

az network nic ip-config create \
  --resource-group "$RESOURCE_GROUP" --nic-name "$NIC_NAME" --name "$IP_CONFIG_V6" \
  --vnet-name "$VNET_NAME" --subnet "$SUBNET_NAME" \
  --private-ip-address-version IPv6 \
  --public-ip-address "$PIP_V6_NAME" \
  --output table

echo "--- VM (Standard_B2ms, Ubuntu 22.04 LTS) ---"
az vm create \
  --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
  --nics "$NIC_NAME" \
  --image Ubuntu2204 \
  --size "$VM_SIZE" \
  --admin-username "$ADMIN_USER" \
  --ssh-key-values "$SSH_KEY_PATH" \
  --output table

VM_IPV4="$(az network public-ip show -g "$RESOURCE_GROUP" -n "$PIP_V4_NAME" --query ipAddress -o tsv)"
VM_IPV6="$(az network public-ip show -g "$RESOURCE_GROUP" -n "$PIP_V6_NAME" --query ipAddress -o tsv)"

echo ""
echo "=== Done ==="
echo "VM public IPv4: ${VM_IPV4}"
echo "VM public IPv6: ${VM_IPV6}"
echo "SSH: ssh -i ~/.ssh/ekadai_azure_vm ${ADMIN_USER}@${VM_IPV4}"
echo ""
echo "If your IP changes later, update the SSH rule with:"
echo "  az network nsg rule update -g $RESOURCE_GROUP --nsg-name $NSG_NAME --name allow-ssh --source-address-prefixes <new-ip>/32"
echo ""
echo "Cost discipline (§6) — pause the VM between sessions:"
echo "  az vm deallocate -g $RESOURCE_GROUP -n $VM_NAME"
echo "  az vm start -g $RESOURCE_GROUP -n $VM_NAME"
