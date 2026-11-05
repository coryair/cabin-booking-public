import { useEffect, useState } from "react";

export interface BrowserLocation {
  pathname: string;
  search: string;
}

function readLocation(): BrowserLocation {
  return {
    pathname: window.location.pathname,
    search: window.location.search,
  };
}

export function navigateTo(path: string, options: { replace?: boolean } = {}): void {
  const current = `${window.location.pathname}${window.location.search}`;
  if (current === path) return;

  if (options.replace) {
    window.history.replaceState({}, "", path);
  } else {
    window.history.pushState({}, "", path);
  }
  window.scrollTo({ top: 0, behavior: "auto" });
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function useBrowserLocation(): BrowserLocation {
  const [location, setLocation] = useState(readLocation);

  useEffect(() => {
    const update = () => setLocation(readLocation());
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);

  return location;
}
