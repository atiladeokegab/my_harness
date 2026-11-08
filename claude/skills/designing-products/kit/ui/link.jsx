import { Link as AriaLink } from 'react-aria-components';
import './kit.css';
import './link.css';

// A real <a> when href is set. A link has no loading state: navigation belongs to the browser.
export function Link({ className = '', ...props }) {
  return <AriaLink {...props} className={`kit-focus kit-link ${className}`} />;
}
