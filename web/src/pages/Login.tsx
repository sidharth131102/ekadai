import { motion } from "framer-motion";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { fadeIn } from "../lib/motion";
import styles from "./AuthLayout.module.css";

export default function Login() {
  const { login } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login({ email, password });
      showToast("Welcome back.", "success");
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={[styles.blob, styles.blob1].join(" ")} />
      <div className={[styles.blob, styles.blob2].join(" ")} />
      <motion.div className={styles.card} variants={fadeIn} initial="hidden" animate="visible">
        <div className={styles.eyebrow}>Welcome back</div>
        <h1 className={styles.title}>Sign in</h1>
        <p className={styles.subtitle}>Pick up your cart and orders right where you left them.</p>

        {error && <div className={styles.formError}>{error}</div>}

        <form className={styles.form} onSubmit={handleSubmit}>
          <Input
            label="Email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
          <Input
            label="Password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          <Button type="submit" fullWidth size="lg" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className={styles.footerText}>
          New here?{" "}
          <Link to="/register" className={styles.footerLink}>
            Create an account
          </Link>
        </p>
      </motion.div>
    </div>
  );
}
