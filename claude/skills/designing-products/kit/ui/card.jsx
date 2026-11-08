import { Link } from 'react-aria-components';
import './kit.css';
import './card.css';

// A panel for peer items. With href the whole card is one link (hover, focus, press, disabled);
// isPending holds its size with placeholder lines while the content loads. Never nest a card in a card.
export function Card({ href, isPending = false, isDisabled, className = '', children, ...props }) {
  const cls = `kit-card ${href ? 'kit-focus kit-card--link' : ''} ${className}`;
  const body = isPending
    ? <><span className="kit-card__line" /><span className="kit-card__line kit-card__line--short" /></>
    : children;
  if (href) return <Link {...props} href={href} isDisabled={isDisabled} aria-busy={isPending || undefined} className={cls}>{body}</Link>;
  return <article {...props} aria-busy={isPending || undefined} className={cls}>{body}</article>;
}
