"use strict";

const releaseManifestUrl = new URL("../../release.json", document.currentScript.src);

function setReleaseStatus(text, isError = false) {
  document.querySelectorAll("[data-latest-release]").forEach((element) => {
    element.textContent = text;
    element.classList.toggle("error", isError);
  });
}

async function loadLatestRelease() {
  try {
    const response = await fetch(releaseManifestUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Release manifest returned ${response.status}`);
    }

    const release = await response.json();
    if (!release.latestVersion) {
      setReleaseStatus("No signed pilot release has been published yet.");
      return;
    }

    setReleaseStatus(`Latest signed release: ${release.latestVersion}`);

    const list = document.querySelector("[data-download-list]");
    if (!list) {
      return;
    }
    const restricted = document.createElement("p");
    restricted.className = "empty-state";
    restricted.textContent = "Request this release by email from the project owner.";
    list.replaceChildren(restricted);
  } catch (error) {
    setReleaseStatus("Release information is temporarily unavailable.", true);
    console.error("Unable to load release information", error);
  }
}

loadLatestRelease();