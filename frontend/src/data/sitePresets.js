/**
 * The website's content, as it ships.
 *
 * An exact mirror of PRESETS in backend/app/services/site_service.py, generated
 * from it rather than typed out twice.
 *
 * Why the front end carries its own copy
 * -------------------------------------
 * The site used to render only what `GET /site` returned, so if that call
 * failed the page collapsed to a headline and a button. Two ordinary things
 * cause that failure, and neither is rare:
 *
 *   - the API is asleep. A free-tier host spins a service down after a quiet
 *     spell and takes the better part of a minute to wake. That minute lands on
 *     a first-time visitor, on the one page where a first impression is the
 *     entire job.
 *   - the migration has not been run yet, so the content tables do not exist.
 *
 * Now these presets render immediately, from the bundle, and the API response
 * is merged over the top when it arrives. A visitor always sees a complete
 * website; an edited block simply replaces its preset a moment later. The site
 * is never worse than this file.
 *
 * Keep in step with the server presets. If they drift, the server wins at
 * runtime - it is merged second - so the risk is a brief flash of old wording,
 * not a wrong page.
 */

export const SITE_BLOCK_ORDER = [
  "brand",
  "hero",
  "trust",
  "problem",
  "features",
  "screenshots",
  "how",
  "pricing",
  "testimonials",
  "faq",
  "cta",
  "contact",
  "footer",
  "seo"
]

export const SITE_PRESETS = {
  "brand": {
    "name": "PGuru",
    "tagline": "PG and hostel operations, on one screen",
    "logo_slot": "logo",
    "company": "Dygine",
    "company_url": "https://dygine.com",
    "show_company": true
  },
  "hero": {
    "headline": "Every bed, every rupee, every branch.",
    "subheadline": "Rooms, residents, rent and complaints in one place - with a login for every tenant and a public listing that fills your empty beds.",
    "primary_label": "Open the app",
    "primary_href": "/login",
    "secondary_label": "Find a PG",
    "secondary_href": "/find-pg",
    "image_slot": "hero"
  },
  "trust": {
    "items": [
      {
        "value": "Bed-level",
        "label": "occupancy, not room-level guesswork"
      },
      {
        "value": "Every tenant",
        "label": "gets their own portal login"
      },
      {
        "value": "UPI · Cash · Bank",
        "label": "all recorded the same way"
      },
      {
        "value": "Multi-branch",
        "label": "one dashboard across properties"
      }
    ]
  },
  "problem": {
    "title": "What it replaces",
    "intro": "Most PGs run on a register, a WhatsApp group and a month-end evening with a calculator. None of those tell you which bed is free tonight.",
    "items": [
      {
        "before": "A register in the drawer",
        "after": "Every resident, room and bed, searchable from your phone"
      },
      {
        "before": "Chasing rent on WhatsApp",
        "after": "Dues, receipts and reminders that keep their own score"
      },
      {
        "before": "“Is 204-B free?”",
        "after": "Live bed status across every branch"
      },
      {
        "before": "Complaints lost in chat",
        "after": "A ticket per complaint, with who closed it and when"
      }
    ]
  },
  "features": {
    "title": "What's inside",
    "items": [
      {
        "icon": "bed",
        "image_slot": "feature-beds",
        "title": "Rooms and beds",
        "text": "Buildings, floors, rooms and individual beds. Vacant, occupied, on notice or under maintenance - at a glance, per branch."
      },
      {
        "icon": "users",
        "title": "Residents and KYC",
        "text": "Full profiles, stay history and scanned ID documents held against each resident, behind their own permission."
      },
      {
        "icon": "rupee",
        "image_slot": "feature-rent",
        "title": "Rent and payments",
        "text": "Invoices, part payments, dues and receipts. UPI, cash and bank transfers all recorded the same way."
      },
      {
        "icon": "portal",
        "image_slot": "feature-portal",
        "title": "A portal for every tenant",
        "text": "Residents see their rent, raise complaints, book laundry and give notice themselves - instead of messaging you."
      },
      {
        "icon": "search",
        "title": "Public listing",
        "text": "Show your free beds to people searching nearby. Enquiries land in your inbox. No broker, no commission."
      },
      {
        "icon": "shield",
        "title": "Roles and permissions",
        "text": "A manager, a warden and an accountant should not see the same screens. Build the roles you actually have."
      }
    ]
  },
  "screenshots": {
    "title": "The product, not a mockup",
    "items": [
      {
        "image_slot": "shot-dashboard",
        "caption": "Owner dashboard - occupancy and collections"
      },
      {
        "image_slot": "shot-beds",
        "caption": "Bed grid, live across every branch"
      },
      {
        "image_slot": "shot-findpg",
        "caption": "Find a PG - public search with a real map"
      },
      {
        "image_slot": "shot-portal",
        "caption": "The resident's own portal"
      }
    ]
  },
  "how": {
    "title": "How it works",
    "steps": [
      {
        "title": "Create your PG",
        "text": "Branches, buildings, floors, rooms and beds. Bulk-create rooms so this takes minutes, not an afternoon."
      },
      {
        "title": "Add your residents",
        "text": "Details, documents and bed assignment. Each one gets a portal login."
      },
      {
        "title": "Set rent once",
        "text": "Due dates and amounts. Invoices and reminders then run themselves."
      },
      {
        "title": "Fill empty beds",
        "text": "Publish your free beds to the public search and take enquiries directly."
      }
    ]
  },
  "pricing": {
    "title": "Pricing",
    "intro": "Monthly, per organisation. Every plan includes the resident portal and the public listing.",
    "note": "Prices in Indian rupees. Taxes as applicable.",
    "cta_label": "Start free",
    "cta_href": "/signup",
    "plans": [
      {
        "name": "Starter",
        "price": "1499",
        "period": "month",
        "summary": "1 branch · up to 60 beds",
        "popular": "",
        "features": "Rooms & beds, Residents, Rent & payments, Complaints, Basic reports"
      },
      {
        "name": "Professional",
        "price": "3999",
        "period": "month",
        "summary": "3 branches · up to 300 beds",
        "popular": "yes",
        "features": "Everything in Starter, Multi-branch, Custom roles, Attendance & QR gate, Food & laundry, Visitors, Expenses"
      },
      {
        "name": "Business",
        "price": "8999",
        "period": "month",
        "summary": "10 branches · up to 1,200 beds",
        "popular": "",
        "features": "Everything in Professional, Assets & inventory, Advanced reports, Audit log export, Announcement targeting"
      },
      {
        "name": "Enterprise",
        "price": "19999",
        "period": "month",
        "summary": "50 branches · up to 8,000 beds",
        "popular": "",
        "features": "Everything in Business, Franchise grouping, API access, Custom SLA, Onboarding assistance"
      }
    ]
  },
  "testimonials": {
    "title": "What owners say",
    "items": []
  },
  "faq": {
    "title": "Questions",
    "items": [
      {
        "q": "Do my residents need to install anything?",
        "a": "No. The resident portal opens in any browser. There is an Android app as well, for anyone who prefers one."
      },
      {
        "q": "Can I run more than one PG?",
        "a": "Yes. Branches are built in from the start, and the dashboard totals across all of them or filters to one."
      },
      {
        "q": "What happens to my data if I stop?",
        "a": "It stays yours. Residents, payments and reports can be exported at any time."
      },
      {
        "q": "Is my tenants' ID data safe?",
        "a": "Scanned documents sit behind a separate permission, so only staff you explicitly allow can view them. Everything travels over HTTPS."
      }
    ]
  },
  "cta": {
    "headline": "Start with one branch.",
    "text": "Set up your rooms and beds, add a few residents, and see a month through. Nothing to install.",
    "primary_label": "Create your account",
    "primary_href": "/signup",
    "secondary_label": "Download for Android",
    "secondary_href": "/pgguru.apk",
    "image_slot": "cta"
  },
  "contact": {
    "title": "Talk to us",
    "phone": "",
    "whatsapp": "",
    "email": "hello@dygine.com",
    "address": "",
    "hours": "Monday to Saturday, 10am - 7pm IST",
    "map_url": ""
  },
  "footer": {
    "legal_name": "",
    "links": [
      {
        "label": "Find a PG",
        "href": "/find-pg"
      },
      {
        "label": "Sign in",
        "href": "/login"
      },
      {
        "label": "Privacy",
        "href": "/privacy"
      },
      {
        "label": "Terms",
        "href": "/terms"
      }
    ],
    "copyright": ""
  },
  "seo": {
    "title": "PGuru - PG and hostel management software for Indian owners",
    "description": "Manage rooms, beds, residents, rent and complaints across every branch. A portal for each tenant and a public listing that fills empty beds. Web and Android.",
    "keywords": "PG management software, hostel management software India, paying guest software, PG software Bengaluru, bed management",
    "canonical": "https://pgguru.in/",
    "social_image_slot": "social",
    "locale": "en_IN"
  }
}

export const SITE_PRESET_IMAGES = {
  "logo": {
    "slot": "logo",
    "src": "/pgguru-logo.png",
    "alt_text": "PGuru",
    "preset": true
  },
  "hero": {
    "slot": "hero",
    "src": "https://picsum.photos/seed/pgguru-hero-room/1400/1000",
    "alt_text": "A bright shared room in a well-run PG",
    "preset": true
  },
  "shot-dashboard": {
    "slot": "shot-dashboard",
    "src": "https://picsum.photos/seed/pgguru-dashboard/1200/780",
    "alt_text": "The owner dashboard: occupancy and collections",
    "preset": true
  },
  "shot-beds": {
    "slot": "shot-beds",
    "src": "https://picsum.photos/seed/pgguru-beds/1200/780",
    "alt_text": "The bed grid, live across every branch",
    "preset": true
  },
  "shot-findpg": {
    "slot": "shot-findpg",
    "src": "https://picsum.photos/seed/pgguru-findpg/1200/780",
    "alt_text": "Find a PG: public search on a real map",
    "preset": true
  },
  "shot-portal": {
    "slot": "shot-portal",
    "src": "https://picsum.photos/seed/pgguru-portal/1200/780",
    "alt_text": "The resident's own portal",
    "preset": true
  },
  "feature-beds": {
    "slot": "feature-beds",
    "src": "https://picsum.photos/seed/pgguru-feature-beds/900/600",
    "alt_text": "Rooms and beds",
    "preset": true
  },
  "feature-rent": {
    "slot": "feature-rent",
    "src": "https://picsum.photos/seed/pgguru-feature-rent/900/600",
    "alt_text": "Rent and payments",
    "preset": true
  },
  "feature-portal": {
    "slot": "feature-portal",
    "src": "https://picsum.photos/seed/pgguru-feature-portal/900/600",
    "alt_text": "A portal for every resident",
    "preset": true
  },
  "cta": {
    "slot": "cta",
    "src": "https://picsum.photos/seed/pgguru-cta/1600/700",
    "alt_text": "A PG common area",
    "preset": true
  },
  "social": {
    "slot": "social",
    "src": "https://picsum.photos/seed/pgguru-social/1200/630",
    "alt_text": "PGuru - PG and hostel management",
    "preset": true
  }
}
