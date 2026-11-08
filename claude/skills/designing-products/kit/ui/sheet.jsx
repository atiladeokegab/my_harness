import { Dialog as AriaDialog, Button, Heading, Modal, ModalOverlay } from 'react-aria-components';
import './kit.css';
import './dialog.css';
import './sheet.css';

export { DialogTrigger as SheetTrigger } from 'react-aria-components';

// A dialog docked to the inline end edge: filters, details, a form beside the work. Same focus rules as Dialog.
export function Sheet({ title, children, className = '', ...props }) {
  return (
    <ModalOverlay isDismissable {...props} className="kit-scrim kit-scrim--sheet">
      <Modal className={`kit-sheet ${className}`}>
        <AriaDialog className="kit-dialog__inner kit-sheet__inner">
          {(state) => (
            <>
              <div className="kit-sheet__head">
                <Heading slot="title" className="kit-dialog__title">{title}</Heading>
                <Button slot="close" aria-label="Close" className="kit-focus kit-icon-button">
                  <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg>
                </Button>
              </div>
              {typeof children === 'function' ? children(state) : children}
            </>
          )}
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}
