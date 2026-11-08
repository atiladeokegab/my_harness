import { createRoot } from 'react-dom/client';
import { Button } from '../ui/button.jsx';
import { Link } from '../ui/link.jsx';
import { Input } from '../ui/input.jsx';
import { Select } from '../ui/select.jsx';
import { Dialog, DialogTrigger } from '../ui/dialog.jsx';
import { Sheet, SheetTrigger } from '../ui/sheet.jsx';
import { Tab, TabList, TabPanel, Tabs } from '../ui/tabs.jsx';
import { Tooltip } from '../ui/tooltip.jsx';
import { ToastRegion, toasts } from '../ui/toast.jsx';
import { Card } from '../ui/card.jsx';
import './page.css';

// The fixture: every kit piece in its states, worded as the brand's own screen. copy.json per brand.
const c = window.COPY;
const still = new URLSearchParams(location.search).has('still'); // captures: tooltip held open

function Page() {
  const f = c.fields, b = c.buttons;
  return (
    <>
      <header className="fx-bar">
        <span className="fx-name">{c.name}</span>
        <nav className="fx-nav" aria-label="Main">{c.nav.map((n, i) => <Link key={n} href="#" aria-current={i === 0 ? 'page' : undefined}>{n}</Link>)}</nav>
        <Button variant="secondary">{c.primary}</Button>
      </header>
      <main className="fx-main">
        <div className="fx-head">
          <h1 className="fx-title">{c.nav[0]}</h1>
          <p className="fx-lead">{c.intro} <Link href="#">{c.introLink}</Link>. <Link isDisabled>{c.disabledLink}</Link></p>
        </div>
        <section className="fx-form" aria-labelledby="form-title">
          <h2 id="form-title" className="fx-h2">{c.formTitle}</h2>
          <Input label={f.amount} defaultValue={f.amountValue} />
          <Input label={f.donor} defaultValue="Priya Shah" isInvalid errorMessage={f.donorError} />
          <Input label={f.charity} defaultValue={f.charityValue} description={f.charityHint} isPending />
          <Input label={f.ref} placeholder={f.refValue} isDisabled />
          <Select label={f.fund} items={f.funds.map((name, i) => ({ id: i, name }))} defaultSelectedKey={0} />
          <Select label={f.fundLoading} items={[]} placeholder="…" isPending />
          <div className="fx-actions">
            <Button>{b.save}</Button>
            <Button variant="secondary">{b.draft}</Button>
            <Button variant="quiet">{b.cancel}</Button>
            <Button variant="secondary" isPending>{b.saving}</Button>
            <Button variant="secondary" isDisabled>{b.locked}</Button>
          </div>
          {/* Last in its column with open space below, so the held-open tooltip in captures covers nothing. */}
          <Tooltip content={c.tip} placement="bottom start" defaultOpen={still}>
            <Button variant="quiet" className="fx-tip">{c.tipLabel}</Button>
          </Tooltip>
        </section>
        <section className="fx-list" aria-label={c.nav[0]}>
          <div className="fx-row">
            <DialogTrigger>
              <Button variant="secondary">{c.dialog.open}</Button>
              <Dialog title={c.dialog.title}>
                {({ close }) => (
                  <>
                    <p className="fx-p">{c.dialog.body}</p>
                    <div className="kit-dialog__actions">
                      <Button variant="secondary" onPress={close}>{c.dialog.cancel}</Button>
                      <Button onPress={close}>{c.dialog.confirm}</Button>
                    </div>
                  </>
                )}
              </Dialog>
            </DialogTrigger>
            <SheetTrigger>
              <Button variant="secondary">{c.sheet.open}</Button>
              <Sheet title={c.sheet.title}>
                {({ close }) => (
                  <>
                    <Input label={c.sheet.field} />
                    <Button onPress={close}>{c.sheet.apply}</Button>
                  </>
                )}
              </Sheet>
            </SheetTrigger>
          </div>
          <Tabs>
            <TabList aria-label={c.formTitle}>
              {c.tabs.map((t, i) => <Tab key={t} id={t} isDisabled={i === 2}>{t}</Tab>)}
            </TabList>
            <TabPanel id={c.tabs[0]} className="fx-cards">
              {c.cards.map(([title, meta]) => (
                <Card key={title} href="#"><span className="fx-card-title">{title}</span><span className="fx-meta">{meta}</span></Card>
              ))}
              <Card isPending />
            </TabPanel>
            <TabPanel id={c.tabs[1]} isPending />
            <TabPanel id={c.tabs[2]} />
          </Tabs>
        </section>
      </main>
      <ToastRegion />
    </>
  );
}

// An identifier (a service, a hash) is set in .kit-id so it never breaks across lines.
for (const t of c.toasts) toasts.add({ ...t, title: t.id ? <>{t.title} <span className="kit-id">{t.id}</span></> : t.title });
document.documentElement.lang = c.lang;
createRoot(document.getElementById('root')).render(<Page />);
