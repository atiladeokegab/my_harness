import { Tooltip as AriaTooltip, TooltipTrigger } from 'react-aria-components';
import './kit.css';
import './tooltip.css';

// Wraps one focusable kit piece (a Button). Shows on hover after a delay and at once on keyboard focus;
// Escape hides it. Never put the only copy of an instruction in a tooltip: touch has no hover.
export function Tooltip({ content, children, placement = 'top', ...props }) {
  return (
    <TooltipTrigger delay={500} {...props}>
      {children}
      <AriaTooltip placement={placement} offset={6} className="kit-tooltip">{content}</AriaTooltip>
    </TooltipTrigger>
  );
}
