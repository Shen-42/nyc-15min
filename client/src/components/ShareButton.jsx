import { useEffect, useState } from "react";

// "Share": the page's address already holds the spot (?lat=...&lng=...).
// On phones it opens the system share sheet; elsewhere it copies the link
// and says so for a moment (heuristic 7: a shortcut for a common task).
export default function ShareButton() {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  async function share() {
    const url = window.location.href;
    // The share sheet only on touch screens: on a laptop, some browsers'
    // share menus are less handy than a copied link.
    if (navigator.share && window.matchMedia("(pointer: coarse)").matches) {
      try {
        await navigator.share({ title: "NYC 15-Minute City Explorer", url });
      } catch {
        // Closed the share sheet: nothing to do.
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      window.prompt("Copy this link:", url); // clipboard blocked: show it instead
    }
  }

  return (
    <>
      <button type="button" className="button button--link score-actions__share" onClick={share}>
        {copied ? "Link copied" : "Share"}
      </button>
      {/* Screen readers don't hear a button's text change; this they do. */}
      <span className="visually-hidden" role="status">
        {copied ? "Link copied" : ""}
      </span>
    </>
  );
}
