import { Button as AriaButton, ProgressBar } from 'react-aria-components';
import './kit.css';
import './button.css';

// variant: primary (the one action on a screen), secondary, quiet. isPending shows a spinner and keeps focus.
export function Button({ variant = 'primary', className = '', children, ...props }) {
  return (
    <AriaButton {...props} className={`kit-focus kit-button kit-button--${variant} ${className}`}>
      {({ isPending }) => (
        <>
          {isPending && <ProgressBar aria-label="Working" isIndeterminate className="kit-spinner" />}
          {children}
        </>
      )}
    </AriaButton>
  );
}
