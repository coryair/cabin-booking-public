interface ScrollElement {
  getBoundingClientRect: () => { top: number };
}

interface ScrollContainer extends ScrollElement {
  scrollTop: number;
}

export function scrollCalendarMonthIntoContainer(container: ScrollContainer, target: ScrollElement) {
  const containerTop = container.getBoundingClientRect().top;
  const targetTop = target.getBoundingClientRect().top;

  container.scrollTop += targetTop - containerTop;
}
