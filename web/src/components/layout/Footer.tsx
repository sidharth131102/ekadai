import styles from "./Footer.module.css";

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <span className={styles.wordmark}>ekadai</span>
        <span className={styles.tagline}>A small catalog, considered carefully.</span>
      </div>
    </footer>
  );
}
