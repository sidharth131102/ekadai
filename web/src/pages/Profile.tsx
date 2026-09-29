import { motion } from "framer-motion";
import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import {
  useAddresses,
  useCreateAddress,
  useDeleteAddress,
  useUpdateAddress,
} from "../api/hooks/useAddresses";
import { ApiError } from "../api/client";
import type { AddressCreateRequest } from "../api/types";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { staggerContainer, staggerItem } from "../lib/motion";
import { usePageView } from "../lib/usePageView";
import styles from "./Profile.module.css";

const EMPTY_ADDRESS: AddressCreateRequest = {
  address_line1: "",
  city: "",
  state: "",
  postal_code: "",
  country: "US",
  is_default: false,
};

export default function Profile() {
  usePageView("profile");
  const { user } = useAuth();
  const { data: addresses } = useAddresses();
  const createAddress = useCreateAddress();
  const updateAddress = useUpdateAddress();
  const deleteAddress = useDeleteAddress();
  const { showToast } = useToast();

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<AddressCreateRequest>(EMPTY_ADDRESS);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      await createAddress.mutateAsync(form);
      setForm(EMPTY_ADDRESS);
      setShowForm(false);
      showToast("Address saved.", "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not save address.", "error");
    }
  }

  async function handleSetDefault(addressId: string) {
    try {
      await updateAddress.mutateAsync({ addressId, payload: { is_default: true } });
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not update address.", "error");
    }
  }

  async function handleDelete(addressId: string) {
    try {
      await deleteAddress.mutateAsync(addressId);
      showToast("Address removed.", "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not remove address.", "error");
    }
  }

  return (
    <div className={["container", styles.page].join(" ")}>
      <h1 className={styles.heading}>Profile</h1>
      <p className={styles.subheading}>{user?.email}</p>

      <div className={styles.sectionHead}>
        <h2 className={styles.sectionTitle}>Saved addresses</h2>
        {!showForm && (
          <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={() => setShowForm(true)}>
            Add address
          </Button>
        )}
      </div>

      {showForm && (
        <motion.form
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          onSubmit={handleSubmit}
          className={styles.form}
        >
          <Input
            label="Address line 1"
            required
            value={form.address_line1}
            onChange={(e) => setForm({ ...form, address_line1: e.target.value })}
          />
          <Input
            label="City"
            required
            value={form.city}
            onChange={(e) => setForm({ ...form, city: e.target.value })}
          />
          <Input
            label="State"
            required
            value={form.state}
            onChange={(e) => setForm({ ...form, state: e.target.value })}
          />
          <Input
            label="Postal code"
            required
            value={form.postal_code}
            onChange={(e) => setForm({ ...form, postal_code: e.target.value })}
          />
          <Input
            label="Country (2-letter)"
            required
            maxLength={2}
            value={form.country}
            onChange={(e) => setForm({ ...form, country: e.target.value.toUpperCase() })}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 8, alignSelf: "end" }}>
            <input
              type="checkbox"
              id="profile-is-default"
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
            />
            <label htmlFor="profile-is-default" style={{ fontSize: "var(--fs-sm)" }}>
              Set as default
            </label>
          </div>
          <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end", gap: 12 }}>
            <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createAddress.isPending}>
              {createAddress.isPending ? "Saving…" : "Save address"}
            </Button>
          </div>
        </motion.form>
      )}

      <motion.div className={styles.addressGrid} variants={staggerContainer} initial="hidden" animate="visible">
        {addresses?.map((address) => (
          <motion.div key={address.address_id} variants={staggerItem} className={styles.addressCard}>
            {address.is_default && <Badge tone="accent">Default</Badge>}
            <span className={styles.addressLines}>
              {address.address_line1}
              {address.address_line2 ? `, ${address.address_line2}` : ""}
              <br />
              {address.city}, {address.state} {address.postal_code}
              <br />
              {address.country}
            </span>
            <div className={styles.addressActions}>
              {!address.is_default && (
                <button className={styles.linkButton} onClick={() => handleSetDefault(address.address_id)}>
                  Set default
                </button>
              )}
              <button
                className={[styles.linkButton, styles.linkButtonDanger].join(" ")}
                onClick={() => handleDelete(address.address_id)}
              >
                Delete
              </button>
            </div>
          </motion.div>
        ))}
      </motion.div>

      {addresses && addresses.length === 0 && !showForm && (
        <p style={{ color: "var(--color-ink-muted)" }}>No saved addresses yet.</p>
      )}
    </div>
  );
}
