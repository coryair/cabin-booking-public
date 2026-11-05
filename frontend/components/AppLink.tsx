import type { ComponentPropsWithoutRef, MouseEvent } from "react";
import { navigateTo } from "../routing";

type AppLinkProps = ComponentPropsWithoutRef<"a">;

export function AppLink({ href, onClick, target, ...props }: AppLinkProps) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (
      event.defaultPrevented
      || event.button !== 0
      || event.metaKey
      || event.ctrlKey
      || event.shiftKey
      || event.altKey
      || target === "_blank"
      || !href?.startsWith("/")
      || href.startsWith("//")
    ) {
      return;
    }

    event.preventDefault();
    navigateTo(href);
  };

  return <a {...props} href={href} target={target} onClick={handleClick} />;
}
