import { Dialog as AriaDialog, DialogTrigger, Heading, Modal, ModalOverlay } from 'react-aria-components';
import './kit.css';
import './dialog.css';

export { DialogTrigger };

// Put inside <DialogTrigger> after its button. Traps focus, closes on Escape or a click outside,
// and gives focus back to the trigger. children may be ({ close }) => ...
export function Dialog({ title, children, className = '', ...props }) {
  return (
    <ModalOverlay isDismissable {...props} className="kit-scrim">
      <Modal className={`kit-dialog ${className}`}>
        <AriaDialog className="kit-dialog__inner">
          {(state) => (
            <>
              <Heading slot="title" className="kit-dialog__title">{title}</Heading>
              {typeof children === 'function' ? children(state) : children}
            </>
          )}
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}
