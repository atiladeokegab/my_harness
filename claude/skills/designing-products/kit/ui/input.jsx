import { FieldError, Input as AriaInput, Label, Text, TextField } from 'react-aria-components';
import './kit.css';
import './input.css';

// A labelled text field. isPending (a server check running) shows a spinner and sets aria-busy.
export function Input({ label, description, errorMessage, isPending = false, className = '', ...props }) {
  return (
    <TextField {...props} className={`kit-field ${className}`}>
      <Label className="kit-field__label">{label}</Label>
      <div className="kit-field__control">
        <AriaInput className="kit-focus kit-input" aria-busy={isPending || undefined} />
        {isPending && <span className="kit-spinner kit-field__spinner" aria-hidden="true" />}
      </div>
      {description && <Text slot="description" className="kit-field__hint">{description}</Text>}
      <FieldError className="kit-field__error">{errorMessage}</FieldError>
    </TextField>
  );
}
