// React Aria's toast is still exported as UNSTABLE_ in the pinned version; only this file names it.
import {
  Button, Text, UNSTABLE_Toast as AriaToast, UNSTABLE_ToastContent as ToastContent,
  UNSTABLE_ToastQueue as ToastQueue, UNSTABLE_ToastRegion as AriaToastRegion,
} from 'react-aria-components';
import './kit.css';
import './toast.css';

// toasts.add({ title, description, tone: 'success' | 'danger' | 'info' | 'pending' }, { timeout: 5000 })
// A tone always shows a word as well as a colour. 'pending' shows a spinner and has no timeout.
export const toasts = new ToastQueue({ maxVisibleToasts: 3 });
const WORD = { success: 'Done', danger: 'Failed', info: 'Note', pending: 'Working' };

export function ToastRegion({ queue = toasts }) {
  return (
    <AriaToastRegion queue={queue} className="kit-toasts">
      {({ toast }) => {
        const tone = toast.content.tone ?? 'info';
        return (
          <AriaToast toast={toast} className={`kit-focus kit-toast kit-toast--${tone}`}>
            {tone === 'pending' ? <span className="kit-spinner kit-toast__mark" aria-hidden="true" /> : <span className="kit-toast__mark" aria-hidden="true" />}
            <ToastContent className="kit-toast__content">
              <Text slot="title" className="kit-toast__title"><span className="kit-toast__word">{WORD[tone]}</span> {toast.content.title}</Text>
              {toast.content.description && <Text slot="description" className="kit-toast__body">{toast.content.description}</Text>}
            </ToastContent>
            <Button slot="close" aria-label="Dismiss" className="kit-focus kit-toast__close kit-icon-button">
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg>
            </Button>
          </AriaToast>
        );
      }}
    </AriaToastRegion>
  );
}
