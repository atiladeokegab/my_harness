import { Tab as AriaTab, TabList as AriaTabList, TabPanel as AriaTabPanel, Tabs as AriaTabs } from 'react-aria-components';
import './kit.css';
import './tabs.css';

// Arrow keys move between tabs; Tab moves into the panel. A panel still loading takes isPending.
export const Tabs = ({ className = '', ...p }) => <AriaTabs {...p} className={`kit-tabs ${className}`} />;
export const TabList = ({ className = '', ...p }) => <AriaTabList {...p} className={`kit-tablist ${className}`} />;
export const Tab = ({ className = '', ...p }) => <AriaTab {...p} className={`kit-focus kit-tab ${className}`} />;
export function TabPanel({ isPending = false, className = '', children, ...p }) {
  return (
    <AriaTabPanel {...p} aria-busy={isPending || undefined} className={`kit-focus kit-tabpanel ${className}`}>
      {isPending ? <span className="kit-spinner" role="img" aria-label="Loading" /> : children}
    </AriaTabPanel>
  );
}
