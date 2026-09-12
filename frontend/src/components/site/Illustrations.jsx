/**
 * Illustrations for the marketing site.
 *
 * Drawn here rather than fetched, and the reason is a mistake worth recording:
 * the site first shipped pointing at a random-photo service, because that was
 * guaranteed to return *something*. It returned a mountain in fog on the
 * homepage of a PG management product. Guaranteed-to-load was the wrong thing
 * to optimise for.
 *
 * These are the opposite trade, and a better one:
 *
 *   relevant   every drawing is of the thing the section is about - a bunk in a
 *              shared room, a rent receipt, a bed grid, a map pin over a street
 *   on-brand   indigo #373DA6 from the product, gold #F7AC2E from the logo's
 *              "uru", and nothing else
 *   instant    inline SVG in the bundle. No request, no layout shift, no 404,
 *              no CDN, and sharp on any screen at any size
 *   tiny       the whole set is a few KB, against ~150 KB for one stock photo
 *
 * They are also deliberately *illustrations*, not fake screenshots. A drawing
 * says "this is what the product is about". A mocked-up screenshot says "this
 * is what the product looks like", and when the real thing differs, that is a
 * small lie the customer discovers on day one.
 *
 * Real photographs of a real property will beat all of this, and every one of
 * these can be replaced with one from Master -> Website. Until then the site
 * looks considered rather than borrowed.
 */

const INDIGO = '#373DA6'
const INDIGO_D = '#232764'
const INDIGO_L = '#8E9BE3'
const WASH = '#EEF0FB'
const GOLD = '#F7AC2E'
const GOLD_L = '#FDDB99'
const INK = '#1B1E4D'
const PAPER = '#FFFFFF'

const base = (className) => ({
  className, xmlns: 'http://www.w3.org/2000/svg', 'aria-hidden': 'true', focusable: 'false',
})

/* ------------------------------------------------ hero: a shared room, in use */
export function IllustrationRoom({ className = 'w-full h-auto' }) {
  return (
    <svg {...base(className)} viewBox="0 0 520 380" role="img">
      <title>A shared room in a PG, with bunk beds, a window and a study desk</title>
      <rect width="520" height="380" rx="18" fill={WASH} />
      {/* back wall + floor */}
      <path d="M0 286h520v76a18 18 0 0 1-18 18H18a18 18 0 0 1-18-18z" fill="#E2E6F6" />
      {/* window, with morning light */}
      <rect x="42" y="54" width="150" height="118" rx="8" fill={PAPER} stroke={INDIGO_L} strokeWidth="3" />
      <path d="M42 113h150M117 54v118" stroke={INDIGO_L} strokeWidth="3" />
      <path d="M50 62h60v44H50z" fill={GOLD_L} opacity=".55" />
      {/* bunk bed */}
      <g>
        <rect x="238" y="96" width="228" height="16" rx="6" fill={INDIGO} />
        <rect x="246" y="78" width="120" height="20" rx="8" fill={PAPER} stroke={INDIGO_L} strokeWidth="2.5" />
        <rect x="238" y="196" width="228" height="16" rx="6" fill={INDIGO} />
        <rect x="246" y="178" width="120" height="20" rx="8" fill={PAPER} stroke={INDIGO_L} strokeWidth="2.5" />
        <rect x="238" y="96" width="12" height="190" rx="6" fill={INDIGO_D} />
        <rect x="454" y="96" width="12" height="190" rx="6" fill={INDIGO_D} />
        {/* ladder */}
        <path d="M398 112v84M430 112v84M398 134h32M398 158h32M398 182h32"
          stroke={GOLD} strokeWidth="5" strokeLinecap="round" />
        {/* blankets */}
        <path d="M250 112h150v14a8 8 0 0 1-8 8H258a8 8 0 0 1-8-8z" fill={GOLD} opacity=".85" />
        <path d="M250 212h150v14a8 8 0 0 1-8 8H258a8 8 0 0 1-8-8z" fill={INDIGO_L} opacity=".9" />
      </g>
      {/* desk + lamp */}
      <rect x="44" y="206" width="150" height="12" rx="5" fill={INDIGO} />
      <rect x="56" y="218" width="10" height="68" rx="4" fill={INDIGO_D} />
      <rect x="172" y="218" width="10" height="68" rx="4" fill={INDIGO_D} />
      <circle cx="88" cy="186" r="15" fill={GOLD} />
      <path d="M88 201v5" stroke={INDIGO_D} strokeWidth="4" strokeLinecap="round" />
      <rect x="120" y="188" width="52" height="18" rx="4" fill={PAPER} stroke={INDIGO_L} strokeWidth="2.5" />
      {/* occupancy chip */}
      <g className="float-soft">
        <rect x="330" y="252" width="146" height="46" rx="12" fill={PAPER} stroke={INDIGO_L} strokeWidth="2.5" />
        <circle cx="354" cy="275" r="9" fill="#10B981" />
        <rect x="372" y="264" width="84" height="8" rx="4" fill={INK} opacity=".75" />
        <rect x="372" y="280" width="56" height="7" rx="3.5" fill={INDIGO_L} />
      </g>
    </svg>
  )
}

/* -------------------------------------------------- features: the bed grid */
export function IllustrationBeds({ className = 'w-full h-auto' }) {
  const cells = [
    ['#10B981', 1], [INDIGO, 1], [INDIGO, 1], [GOLD, 1],
    [INDIGO, 1], ['#10B981', 1], [INDIGO, 1], [INDIGO, 1],
    [INDIGO, 1], [INDIGO, 1], [GOLD, 1], ['#10B981', 1],
  ]
  return (
    <svg {...base(className)} viewBox="0 0 400 260" role="img">
      <title>A grid of beds showing which are free, occupied or on notice</title>
      <rect width="400" height="260" rx="16" fill={WASH} />
      {cells.map(([c], i) => {
        const x = 34 + (i % 4) * 84
        const y = 44 + Math.floor(i / 4) * 64
        return (
          <g key={i}>
            <rect x={x} y={y} width="68" height="48" rx="10" fill={PAPER}
              stroke={c} strokeWidth="3" />
            <rect x={x + 10} y={y + 14} width="30" height="7" rx="3.5" fill={c} opacity=".85" />
            <circle cx={x + 55} cy={y + 31} r="6" fill={c} />
          </g>
        )
      })}
      <rect x="34" y="16" width="96" height="10" rx="5" fill={INDIGO} opacity=".7" />
    </svg>
  )
}

/* --------------------------------------------------- features: rent receipt */
export function IllustrationRent({ className = 'w-full h-auto' }) {
  return (
    <svg {...base(className)} viewBox="0 0 400 260" role="img">
      <title>A rent receipt marked paid, with a rupee coin</title>
      <rect width="400" height="260" rx="16" fill={WASH} />
      <g className="float-slow">
        <path d="M112 36h176v188l-22-14-22 14-22-14-22 14-22-14-22 14-22-14-22 14z"
          fill={PAPER} stroke={INDIGO_L} strokeWidth="3" />
        <rect x="136" y="66" width="88" height="10" rx="5" fill={INK} opacity=".8" />
        <rect x="136" y="92" width="128" height="8" rx="4" fill={INDIGO_L} />
        <rect x="136" y="112" width="104" height="8" rx="4" fill={INDIGO_L} />
        <rect x="136" y="140" width="128" height="12" rx="6" fill={INDIGO} opacity=".85" />
        <rect x="136" y="164" width="70" height="8" rx="4" fill={INDIGO_L} />
      </g>
      <g className="float-soft">
        <circle cx="298" cy="176" r="38" fill={GOLD} />
        <text x="298" y="192" textAnchor="middle" fontSize="42" fontWeight="700" fill={PAPER}>₹</text>
      </g>
      <circle cx="120" cy="58" r="15" fill="#10B981" />
      <path d="M113 58l5 5 10-10" stroke={PAPER} strokeWidth="3.5"
        strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

/* ------------------------------------------------ features: tenant's portal */
export function IllustrationPortal({ className = 'w-full h-auto' }) {
  return (
    <svg {...base(className)} viewBox="0 0 400 260" role="img">
      <title>A resident's phone showing their rent, complaints and notices</title>
      <rect width="400" height="260" rx="16" fill={WASH} />
      <g className="float-soft">
        <rect x="146" y="26" width="108" height="208" rx="18" fill={INDIGO_D} />
        <rect x="154" y="42" width="92" height="176" rx="10" fill={PAPER} />
        <rect x="182" y="32" width="36" height="5" rx="2.5" fill={INDIGO_L} />
        <rect x="164" y="54" width="52" height="8" rx="4" fill={INK} opacity=".75" />
        <rect x="164" y="74" width="72" height="30" rx="8" fill={GOLD} opacity=".9" />
        <rect x="172" y="84" width="40" height="7" rx="3.5" fill={PAPER} />
        <rect x="164" y="116" width="72" height="22" rx="7" fill={WASH} />
        <rect x="164" y="146" width="72" height="22" rx="7" fill={WASH} />
        <rect x="164" y="176" width="72" height="22" rx="7" fill={WASH} />
        <circle cx="176" cy="127" r="5" fill={INDIGO} />
        <circle cx="176" cy="157" r="5" fill="#10B981" />
        <circle cx="176" cy="187" r="5" fill={GOLD} />
      </g>
      <circle cx="92" cy="86" r="26" fill={INDIGO} opacity=".14" />
      <circle cx="318" cy="184" r="34" fill={GOLD} opacity=".18" />
    </svg>
  )
}

/* --------------------------------------------- features: find a PG, on a map */
export function IllustrationMap({ className = 'w-full h-auto' }) {
  return (
    <svg {...base(className)} viewBox="0 0 400 260" role="img">
      <title>A map with a search pin and nearby PGs marked</title>
      <rect width="400" height="260" rx="16" fill="#E8EEF3" />
      <path d="M0 96h400M0 178h400M104 0v260M268 0v260" stroke={PAPER} strokeWidth="9" />
      <path d="M0 136h400" stroke={PAPER} strokeWidth="5" />
      <circle cx="200" cy="130" r="74" fill={INDIGO} opacity=".08" />
      <circle cx="200" cy="130" r="74" fill="none" stroke={INDIGO} strokeWidth="2" opacity=".4" />
      <circle cx="142" cy="88" r="8" fill="#10B981" stroke={PAPER} strokeWidth="3" />
      <circle cx="264" cy="112" r="8" fill="#10B981" stroke={PAPER} strokeWidth="3" />
      <circle cx="238" cy="196" r="8" fill="#10B981" stroke={PAPER} strokeWidth="3" />
      <g className="float-soft">
        <path d="M200 76a26 26 0 0 1 26 26c0 17-26 48-26 48s-26-31-26-48a26 26 0 0 1 26-26z"
          fill={INDIGO} stroke={PAPER} strokeWidth="4" />
        <circle cx="200" cy="102" r="10" fill={PAPER} />
      </g>
    </svg>
  )
}

/* ------------------------------------------------ features: roles and access */
export function IllustrationRoles({ className = 'w-full h-auto' }) {
  return (
    <svg {...base(className)} viewBox="0 0 400 260" role="img">
      <title>A shield with staff roles, each seeing different screens</title>
      <rect width="400" height="260" rx="16" fill={WASH} />
      <path d="M200 38l70 26v62c0 44-30 74-70 92-40-18-70-48-70-92V64z"
        fill={INDIGO} opacity=".12" stroke={INDIGO} strokeWidth="3" />
      <path d="M176 132l16 17 34-38" stroke={GOLD} strokeWidth="9"
        strokeLinecap="round" strokeLinejoin="round" fill="none" />
      {[[62, 92], [338, 92], [62, 186], [338, 186]].map(([cx, cy], i) => (
        <g key={i}>
          <circle cx={cx} cy={cy} r="20" fill={PAPER} stroke={INDIGO_L} strokeWidth="3" />
          <circle cx={cx} cy={cy - 5} r="6.5" fill={INDIGO} />
          <path d={`M${cx - 10} ${cy + 12}a10 10 0 0 1 20 0z`} fill={INDIGO} />
        </g>
      ))}
    </svg>
  )
}

/* --------------------------------------------- features: documents under 5 KB */
export function IllustrationDocs({ className = 'w-full h-auto' }) {
  return (
    <svg {...base(className)} viewBox="0 0 400 260" role="img">
      <title>An identity document being scanned and stored securely</title>
      <rect width="400" height="260" rx="16" fill={WASH} />
      <g className="float-slow">
        <rect x="96" y="62" width="208" height="132" rx="12" fill={PAPER}
          stroke={INDIGO_L} strokeWidth="3" />
        <circle cx="146" cy="112" r="22" fill={INDIGO} opacity=".22" />
        <circle cx="146" cy="105" r="8" fill={INDIGO} />
        <path d="M132 126a14 14 0 0 1 28 0z" fill={INDIGO} />
        <rect x="184" y="92" width="92" height="9" rx="4.5" fill={INK} opacity=".7" />
        <rect x="184" y="112" width="72" height="8" rx="4" fill={INDIGO_L} />
        <rect x="120" y="152" width="156" height="8" rx="4" fill={INDIGO_L} />
      </g>
      <path d="M74 48v-14a10 10 0 0 1 10-10h16M326 48v-14a10 10 0 0 0-10-10h-16
               M74 208v14a10 10 0 0 0 10 10h16M326 208v14a10 10 0 0 1-10 10h-16"
        stroke={GOLD} strokeWidth="6" strokeLinecap="round" fill="none" />
      <rect x="150" y="204" width="100" height="26" rx="13" fill={INDIGO} />
      <text x="200" y="222" textAnchor="middle" fontSize="13" fontWeight="600" fill={PAPER}>
        under 5 KB
      </text>
    </svg>
  )
}

/** Looked up by the `illustration` name on a preset feature or page section. */
export const ILLUSTRATIONS = {
  room: IllustrationRoom,
  beds: IllustrationBeds,
  rent: IllustrationRent,
  portal: IllustrationPortal,
  map: IllustrationMap,
  roles: IllustrationRoles,
  docs: IllustrationDocs,
}

export const Illustration = ({ name, className }) => {
  const C = ILLUSTRATIONS[name]
  return C ? <C className={className} /> : null
}
