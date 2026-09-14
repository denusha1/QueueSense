'use client';
import { useEffect, useRef, useState } from 'react';
import { ArrowUp } from 'lucide-react';

/** Decorative effects never intercept a control or trigger React renders on pointer movement. */
export function ExperienceEffects() {
 const progress = useRef<HTMLDivElement>(null);
 const [canReturn, setCanReturn] = useState(false);
 useEffect(() => {
  let scrollFrame = 0;
  let pointerFrame = 0;
  let illuminated: HTMLElement | null = null;
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const scroll = () => {
   cancelAnimationFrame(scrollFrame);
   scrollFrame = requestAnimationFrame(() => {
    const available = document.documentElement.scrollHeight - window.innerHeight;
    if (progress.current) progress.current.style.transform = `scaleX(${available > 0 ? Math.min(1, window.scrollY / available) : 0})`;
    setCanReturn(window.scrollY > 600);
   });
  };
  const clear = () => { illuminated?.removeAttribute('data-illuminated'); illuminated = null; };
  const pointer = (event: PointerEvent) => {
   if (motion.matches || !finePointer.matches) { clear(); return; }
   const target = event.target instanceof Element ? event.target.closest<HTMLElement>('.panel, .metric-card, .page-heading, .story, .role-card') : null;
   const { clientX, clientY } = event;
   cancelAnimationFrame(pointerFrame);
   pointerFrame = requestAnimationFrame(() => {
    if (target !== illuminated) clear();
    if (!target) return;
    illuminated = target;
    const bounds = target.getBoundingClientRect();
    target.style.setProperty('--light-x', `${clientX - bounds.left}px`);
    target.style.setProperty('--light-y', `${clientY - bounds.top}px`);
    target.setAttribute('data-illuminated', 'true');
   });
  };
  window.addEventListener('scroll', scroll, { passive: true });
  window.addEventListener('resize', scroll, { passive: true });
  document.addEventListener('pointermove', pointer, { passive: true });
  document.addEventListener('pointerleave', clear);
  motion.addEventListener('change', clear);
  scroll();
  return () => {
   cancelAnimationFrame(scrollFrame); cancelAnimationFrame(pointerFrame); clear();
   window.removeEventListener('scroll', scroll); window.removeEventListener('resize', scroll);
   document.removeEventListener('pointermove', pointer); document.removeEventListener('pointerleave', clear);
   motion.removeEventListener('change', clear);
  };
 }, []);
 return <><div className="reading-progress" ref={progress} aria-hidden="true"/>{canReturn && <button className="return-to-top" aria-label="Back to top" onClick={() => { window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }); const heading = document.querySelector<HTMLElement>('main h1') ?? document.querySelector<HTMLElement>('main h2'); if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus({ preventScroll: true }); } }}><ArrowUp size={19}/><span>Back to top</span></button>}</>;
}
