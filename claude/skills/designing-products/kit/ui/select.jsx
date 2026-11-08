import { Button, Label, ListBox, ListBoxItem, Popover, Select as AriaSelect, SelectValue } from 'react-aria-components';
import './kit.css';
import './select.css';

// items: [{ id, name }]. isPending (options still loading) disables the trigger and shows a spinner.
export function Select({ label, items, isPending = false, isDisabled, className = '', ...props }) {
  return (
    <AriaSelect {...props} isDisabled={isDisabled || isPending} className={`kit-field kit-select ${className}`}>
      <Label className="kit-field__label">{label}</Label>
      <Button className="kit-focus kit-select__trigger" aria-busy={isPending || undefined}>
        <SelectValue className="kit-select__value" />
        {isPending
          ? <span className="kit-spinner" aria-hidden="true" />
          : <svg className="kit-select__chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" /></svg>}
      </Button>
      <Popover className="kit-popover" offset={4}>
        <ListBox className="kit-listbox" items={items}>
          {(item) => <ListBoxItem className="kit-option" id={item.id}>{item.name}</ListBoxItem>}
        </ListBox>
      </Popover>
    </AriaSelect>
  );
}
