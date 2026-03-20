/* ============================================================
   WenZi — GitHub Pages Script
   Scroll-fade animation + GitHub Release version fetch
   ============================================================ */

(function () {
  "use strict";

  // ---------- Intersection Observer for fade-in ----------
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12 }
  );

  document.querySelectorAll(".fade-in").forEach((el) => observer.observe(el));

  // ---------- Fetch latest release from GitHub API ----------
  const REPO = "Airead/WenZi";
  const versionBadge = document.getElementById("version-badge");

  // All standard download buttons (hero + install section)
  const standardBtns = [
    document.getElementById("download-btn"),
    document.getElementById("download-btn-install"),
  ].filter(Boolean);

  // All lite download buttons (hero + install section)
  const liteBtns = [
    document.getElementById("download-lite-btn"),
    document.getElementById("download-lite-btn-install"),
  ].filter(Boolean);

  if (versionBadge || standardBtns.length || liteBtns.length) {
    fetch(`https://api.github.com/repos/${REPO}/releases/latest`)
      .then((res) => {
        if (!res.ok) throw new Error(res.status);
        return res.json();
      })
      .then((release) => {
        const tag = release.tag_name; // e.g. "v0.0.5"

        if (versionBadge) {
          versionBadge.textContent = `Latest: ${tag}`;
        }

        // Standard DMG: matches "WenZi-0.1.0-arm64.dmg" but not "WenZi-Lite-..."
        const standardAsset = release.assets.find(
          (a) => a.name.endsWith(".dmg") && !a.name.includes("Lite")
        );
        // Lite DMG: matches "WenZi-Lite-0.1.0-arm64.dmg"
        const liteAsset = release.assets.find(
          (a) => a.name.endsWith(".dmg") && a.name.includes("Lite")
        );

        const fallback = release.html_url;

        standardBtns.forEach((btn) => {
          btn.href = standardAsset ? standardAsset.browser_download_url : fallback;
        });
        liteBtns.forEach((btn) => {
          btn.href = liteAsset ? liteAsset.browser_download_url : fallback;
        });
      })
      .catch(() => {
        // Silently fall back — buttons keep default Releases link
      });
  }
})();
