import { AnimatePresence, motion } from "framer-motion";
import { Heart, ShoppingBag, User } from "lucide-react";
import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useCart } from "../../api/hooks/useCart";
import { useWishlist } from "../../api/hooks/useWishlist";
import { useAuth } from "../../context/AuthContext";
import { useCartDrawer } from "../../context/CartDrawerContext";
import { scaleIn } from "../../lib/motion";
import styles from "./Header.module.css";

const NAV_LINKS = [
  { to: "/", label: "Home" },
  { to: "/products", label: "Shop" },
  { to: "/wishlist", label: "Wishlist" },
  { to: "/orders", label: "Orders" },
];

export function Header() {
  const { isAuthenticated, user, logout } = useAuth();
  const { data: cart } = useCart();
  const { data: wishlist } = useWishlist();
  const { open: openCart } = useCartDrawer();
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();

  const cartCount = cart?.total_quantity ?? 0;
  const wishlistCount = wishlist?.items.length ?? 0;

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <NavLink to="/" className={styles.logo}>
          eka<span>dai</span>
        </NavLink>

        <nav className={styles.nav}>
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === "/"}
              className={({ isActive }) =>
                [styles.navLink, isActive ? styles.navLinkActive : ""].filter(Boolean).join(" ")
              }
            >
              {({ isActive }) => (
                <>
                  {link.label}
                  {isActive && <motion.span layoutId="nav-underline" className={styles.underline} />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <div className={styles.actions}>
          <button
            type="button"
            className={styles.iconButton}
            onClick={() => navigate("/wishlist")}
            aria-label="Wishlist"
          >
            <Heart size={19} />
            {wishlistCount > 0 && <span className={styles.badge}>{wishlistCount}</span>}
          </button>

          <button type="button" className={styles.iconButton} onClick={openCart} aria-label="Cart">
            <ShoppingBag size={19} />
            <AnimatePresence>
              {cartCount > 0 && (
                <motion.span
                  key={cartCount}
                  className={styles.badge}
                  initial={{ scale: 0 }}
                  animate={{ scale: [1.3, 1] }}
                  exit={{ scale: 0 }}
                >
                  {cartCount}
                </motion.span>
              )}
            </AnimatePresence>
          </button>

          {isAuthenticated ? (
            <div className={styles.userMenuWrap}>
              <button
                type="button"
                className={styles.iconButton}
                onClick={() => setMenuOpen((v) => !v)}
                aria-label="Account menu"
              >
                <User size={19} />
              </button>
              <AnimatePresence>
                {menuOpen && (
                  <motion.div
                    className={styles.userMenu}
                    variants={scaleIn}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    onMouseLeave={() => setMenuOpen(false)}
                  >
                    <div style={{ padding: "0.5rem 0.75rem", fontSize: "var(--fs-xs)", color: "var(--color-ink-muted)" }}>
                      {user?.email}
                    </div>
                    <button
                      className={styles.userMenuItem}
                      onClick={() => {
                        setMenuOpen(false);
                        navigate("/profile");
                      }}
                    >
                      Profile & addresses
                    </button>
                    <button
                      className={styles.userMenuItem}
                      onClick={() => {
                        setMenuOpen(false);
                        navigate("/orders");
                      }}
                    >
                      Order history
                    </button>
                    <button
                      className={styles.userMenuItem}
                      onClick={() => {
                        setMenuOpen(false);
                        logout();
                        navigate("/");
                      }}
                    >
                      Sign out
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ) : (
            <div className={styles.authLinks}>
              <button className={styles.navLink} onClick={() => navigate("/login")}>
                Sign in
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
