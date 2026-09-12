/**
 * /privacy and /terms.
 *
 * Two pages, one file, because they share a layout and are read by the same
 * person in the same five minutes.
 *
 * WHY THIS EXISTS AND WHAT IT IS NOT
 * ----------------------------------
 * The Play Store will not accept an app without a privacy policy at a public
 * URL, and this app handles Aadhaar and PAN scans, live location and payment
 * records - so the policy is not a formality anyone should copy from a
 * template site.
 *
 * What is written here is accurate to what the code actually does. Every claim
 * was checked against the source: the permissions in AndroidManifest.xml, the
 * 5 KB document store in models/customer.py, the geofence in the gate
 * attendance flow, and the Razorpay and Brevo integrations. That accuracy
 * matters beyond honesty - Google cross-checks the Data safety form against
 * observed app behaviour, and a mismatch gets an app pulled.
 *
 * It is NOT legal advice and was not written by a lawyer. India's Digital
 * Personal Data Protection Act 2023 applies to this product, and a PG operator
 * handling identity documents has obligations under it that no template
 * covers. Have a lawyer read this before it carries real weight. It is a
 * correct starting point, not a finished one.
 *
 * The company name, address and contact details come from the `contact` and
 * `footer` blocks, so they stay in step with the rest of the site instead of
 * going stale in a second place.
 */
import { useSite, useReveal } from '@/components/site/SiteLayout'

const UPDATED = '12 September 2026'

function Page({ title, updated, children }) {
  const root = useReveal([])
  return (
    <div ref={root}>
      <section className="wash-brand border-b border-line">
        <div className="max-w-3xl mx-auto px-5 py-14 sm:py-16">
          <p className="text-xs font-semibold uppercase tracking-[.14em] text-accent-600 mb-2.5">
            Legal
          </p>
          <h1 className="text-3xl sm:text-4xl font-semibold tracking-[-.025em]">{title}</h1>
          <p className="mt-3 text-sm text-slate-500">Last updated {updated}</p>
        </div>
      </section>
      <section className="max-w-3xl mx-auto px-5 py-12">
        <div className="prose-legal space-y-9">{children}</div>
      </section>
    </div>
  )
}

const H = ({ children }) => (
  <h2 className="text-xl font-semibold tracking-[-.015em] mb-3">{children}</h2>
)
const P = ({ children }) => (
  <p className="text-slate-600 leading-relaxed mb-3">{children}</p>
)
const UL = ({ children }) => (
  <ul className="space-y-2 mb-3">{children}</ul>
)
const LI = ({ children }) => (
  <li className="text-slate-600 leading-relaxed flex gap-2.5">
    <span className="mt-2 h-1.5 w-1.5 rounded-full bg-accent-400 shrink-0" />
    <span>{children}</span>
  </li>
)

export function Privacy() {
  const site = useSite()
  const c = site.blocks.contact || {}
  const f = site.blocks.footer || {}
  const who = f.legal_name || site.blocks.brand?.name || 'PGuru'
  const email = c.email || 'pgguru.in@gmail.com'

  return (
    <Page title="Privacy policy" updated={UPDATED}>
      <section className="reveal">
        <P>
          PGuru is software that PG and hostel owners use to run their properties. This
          policy explains what the service collects, why, and what happens to it.
        </P>
        <P>
          Two different relationships matter here. When a PG owner signs up, {who} is the
          data fiduciary for their account. When that owner records their residents, the
          owner decides what is collected and why — {who} processes it on their
          instructions. A resident asking for their records should ask their PG first.
        </P>
      </section>

      <section className="reveal">
        <H>What is collected</H>
        <P><b>From PG owners and staff:</b></P>
        <UL>
          <LI>Name, email address, phone number and role</LI>
          <LI>Property details: branches, buildings, rooms and beds</LI>
          <LI>Payment records, invoices and expenses you enter</LI>
        </UL>
        <P><b>From residents, recorded by their PG:</b></P>
        <UL>
          <LI>Name, email, phone, and the bed they occupy</LI>
          <LI>
            Scanned identity documents — Aadhaar, PAN, passport, driving licence or
            voter ID. Stored as images under 5 KB each, at most three per resident.
          </LI>
          <LI>Rent, payment and stay history; complaints, laundry and food bookings</LI>
          <LI>Gate attendance records, including the time of entry and exit</LI>
        </UL>
        <P><b>From people searching for a PG:</b></P>
        <UL>
          <LI>Name, email and phone, once an account is created</LI>
          <LI>The enquiries sent, and which PG received each one</LI>
        </UL>
      </section>

      <section className="reveal">
        <H>Location and camera</H>
        <P>
          The Android app asks for two device permissions, and only uses them for the
          purposes below. Neither runs in the background.
        </P>
        <UL>
          <LI>
            <b>Location</b> — to show PGs near you on the public search, and to confirm a
            resident is physically at the gate when marking attendance. Position is read
            at the moment you tap; the app does not track movement and does not store a
            location history.
          </LI>
          <LI>
            <b>Camera</b> — to scan QR codes at the gate and at first sign-in, and to
            photograph identity documents and property images. A photograph is processed
            on the device, reduced to under 5 KB, and only then uploaded.
          </LI>
        </UL>
      </section>

      <section className="reveal">
        <H>Who else sees it</H>
        <P>
          Data is never sold, and is never used for advertising. It is shared only with
          the services needed to run the product:
        </P>
        <UL>
          <LI><b>Razorpay</b> — when a resident pays online. Card details are entered on Razorpay's own checkout and never reach our servers.</LI>
          <LI><b>Brevo</b> — to send verification codes and password reset emails.</LI>
          <LI><b>Render and Neon</b> — hosting and the database.</LI>
          <LI><b>OpenStreetMap</b> — map tiles and place-name lookups on the public search.</LI>
        </UL>
        <P>
          One PG can never see another PG's data. Residents see only their own records.
          Identity document images sit behind a separate permission, so within a PG only
          staff explicitly granted it can view them.
        </P>
      </section>

      <section className="reveal">
        <H>How long it is kept</H>
        <P>
          Account and resident records are kept while the account is active and for as
          long as the PG needs them for its own tax and legal obligations. A PG can
          delete a resident's documents at any time from the resident's profile.
        </P>
        <P>
          Closing an account removes its data within 90 days, except where a law requires
          it to be kept longer.
        </P>
      </section>

      <section className="reveal">
        <H>Security</H>
        <UL>
          <LI>Everything travels over HTTPS.</LI>
          <LI>Passwords are stored as Argon2 hashes and are not recoverable, by us or anyone else.</LI>
          <LI>Payment gateway keys are encrypted at rest and cannot be read back.</LI>
          <LI>Identity document images require a separate permission to view.</LI>
          <LI>Signing out, changing a password or deactivating an account revokes every session on every device immediately.</LI>
        </UL>
        <P>
          No system is perfect. If we become aware of a breach affecting your data, we
          will tell you and the relevant authority as the law requires.
        </P>
      </section>

      <section className="reveal">
        <H>Your rights</H>
        <P>
          Under India's Digital Personal Data Protection Act 2023 you may ask what is
          held about you, ask for it to be corrected, ask for it to be erased, and
          withdraw consent.
        </P>
        <P>
          If you are a <b>resident</b>, ask your PG first — they control your record. If
          they cannot help, write to us at {email} and we will.
        </P>
      </section>

      <section className="reveal">
        <H>Children</H>
        <P>
          This service is for adults running or living in paying-guest accommodation. It
          is not directed at children under 18, and accounts are not knowingly created
          for them.
        </P>
      </section>

      <section className="reveal">
        <H>Changes</H>
        <P>
          When this policy changes materially, the date at the top changes and account
          holders are notified. Continuing to use the service after that means accepting
          the updated policy.
        </P>
      </section>

      <section className="reveal">
        <H>Contact</H>
        <P>
          Questions about this policy, or a request about your data: <b>{email}</b>
          {c.phone ? <> · {c.phone}</> : null}
        </P>
        {c.address && <P>{c.address}</P>}
      </section>
    </Page>
  )
}

export function Terms() {
  const site = useSite()
  const c = site.blocks.contact || {}
  const f = site.blocks.footer || {}
  const who = f.legal_name || site.blocks.brand?.name || 'PGuru'
  const email = c.email || 'pgguru.in@gmail.com'

  return (
    <Page title="Terms of service" updated={UPDATED}>
      <section className="reveal">
        <H>The agreement</H>
        <P>
          These terms apply to anyone using PGuru — as a PG owner, a member of their
          staff, a resident, or someone searching for a room. Using the service means
          accepting them.
        </P>
      </section>

      <section className="reveal">
        <H>Accounts</H>
        <UL>
          <LI>You are responsible for what happens under your login. Keep your password to yourself.</LI>
          <LI>Give accurate details. An account opened with false information may be closed.</LI>
          <LI>A PG owner is responsible for the staff accounts they create and the permissions they grant.</LI>
        </UL>
      </section>

      <section className="reveal">
        <H>What a PG owner is responsible for</H>
        <P>
          This is the part that matters most, and it is not boilerplate. If you record
          residents on PGuru, you decide what is collected and you answer for it.
        </P>
        <UL>
          <LI>Collect identity documents only with the resident's knowledge and consent.</LI>
          <LI>Only publish a listing for a property you actually operate.</LI>
          <LI>Keep what you publish accurate — rent, availability and amenities.</LI>
          <LI>Grant the permission to view identity documents only to staff who genuinely need it.</LI>
          <LI>Follow the law that applies to you, including India's Digital Personal Data Protection Act 2023 and any local rules on tenant registration.</LI>
        </UL>
      </section>

      <section className="reveal">
        <H>Payment and plans</H>
        <UL>
          <LI>Plans are billed monthly per organisation. Prices are shown on the pricing page and exclude taxes unless stated.</LI>
          <LI>Each plan has limits on branches, beds and staff logins. Exceeding them requires a higher plan.</LI>
          <LI>Rent collected from residents is between the PG and the resident. {who} is not a party to it and does not hold that money.</LI>
          <LI>You can stop using the service at any time. Fees already paid for the current period are not refunded.</LI>
        </UL>
      </section>

      <section className="reveal">
        <H>What is not allowed</H>
        <UL>
          <LI>Using the service to break the law, or to hold data you have no right to hold.</LI>
          <LI>Publishing a listing for a property that does not exist or is not yours.</LI>
          <LI>Attempting to reach another organisation's data, or to probe the service for weaknesses without permission.</LI>
          <LI>Reselling access, or scraping the public search in bulk.</LI>
        </UL>
      </section>

      <section className="reveal">
        <H>Enquiries and listings</H>
        <P>
          The public search shows only PGs that chose to appear. {who} does not verify
          listings, does not inspect properties, and is not an agent or broker for
          either side. An enquiry is an introduction — what follows is between the
          seeker and the PG.
        </P>
        <P>
          Availability is shown as a band such as “a few beds”, never an exact count.
        </P>
      </section>

      <section className="reveal">
        <H>Availability</H>
        <P>
          We work to keep the service running but do not promise it will never be
          unavailable. Maintenance, hosting failures and network problems happen.
        </P>
      </section>

      <section className="reveal">
        <H>Your data</H>
        <P>
          Your data stays yours. You can export residents, payments and reports at any
          time. See the <a href="/privacy" className="text-brand-700 font-medium hover:underline">privacy policy</a> for
          how it is handled.
        </P>
      </section>

      <section className="reveal">
        <H>Liability</H>
        <P>
          The service is provided as it is. To the extent the law allows, {who} is not
          liable for indirect or consequential loss, and total liability in any twelve
          month period is limited to the fees paid in that period.
        </P>
        <P>
          Nothing here limits liability that cannot be limited by law.
        </P>
      </section>

      <section className="reveal">
        <H>Ending it</H>
        <P>
          You may stop at any time. We may suspend or close an account that breaks these
          terms, or that goes unpaid, after telling you where it is reasonable to do so.
        </P>
      </section>

      <section className="reveal">
        <H>Governing law</H>
        <P>
          These terms are governed by the laws of India, and the courts of Bengaluru,
          Karnataka have jurisdiction.
        </P>
      </section>

      <section className="reveal">
        <H>Contact</H>
        <P>
          <b>{email}</b>{c.phone ? <> · {c.phone}</> : null}
        </P>
        {c.address && <P>{c.address}</P>}
      </section>
    </Page>
  )
}
