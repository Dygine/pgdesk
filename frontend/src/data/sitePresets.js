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
  "features_detail",
  "screenshots",
  "how",
  "pricing",
  "pricing_compare",
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
    "illustration": "room"
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
        "illustration": "beds",
        "title": "Rooms and beds",
        "text": "Buildings, floors, rooms and individual beds. Vacant, occupied, on notice or under maintenance - at a glance, per branch."
      },
      {
        "icon": "users",
        "illustration": "docs",
        "title": "Residents and KYC",
        "text": "Full profiles, stay history and scanned ID documents held against each resident, behind their own permission."
      },
      {
        "icon": "rupee",
        "illustration": "rent",
        "title": "Rent and payments",
        "text": "Invoices, part payments, dues and receipts. UPI, cash and bank transfers all recorded the same way."
      },
      {
        "icon": "portal",
        "illustration": "portal",
        "title": "A portal for every tenant",
        "text": "Residents see their rent, raise complaints, book laundry and give notice themselves - instead of messaging you."
      },
      {
        "icon": "search",
        "illustration": "map",
        "title": "Public listing",
        "text": "Show your free beds to people searching nearby. Enquiries land in your inbox. No broker, no commission."
      },
      {
        "icon": "shield",
        "illustration": "roles",
        "title": "Roles and permissions",
        "text": "A manager, a warden and an accountant should not see the same screens. Build the roles you actually have."
      }
    ]
  },
  "features_detail": {
    "title": "In detail",
    "intro": "The whole of a PG's day, not the parts that are easy to build.",
    "groups": [
      {
        "illustration": "beds",
        "title": "Property and beds",
        "text": "Branches, buildings, floors, rooms and individual beds. Bulk-create rooms so setting up a 200-bed hostel is an evening, not a week.",
        "points": "Bed-level status: vacant, occupied, notice, maintenance, Room types and sharing counts, Bulk room creation, Transfers between beds and branches, Blueprint view of the whole property"
      },
      {
        "illustration": "docs",
        "title": "Residents and KYC",
        "text": "Full profiles with stay history and scanned identity documents, held behind their own permission so not every staff member sees them.",
        "points": "Aadhaar, PAN, passport, licence, voter ID, Up to three scans per resident under 5 KB each, Camera capture on any phone, Separate view permission for ID images, Full stay and transfer history"
      },
      {
        "illustration": "rent",
        "title": "Rent, invoices and payments",
        "text": "Set the rent once and the month runs itself. Part payments, dues and receipts all recorded the same way whether the money arrived by UPI or cash.",
        "points": "Automatic monthly invoices, Part payments and outstanding dues, UPI, cash and bank transfer, Digital receipts, Expense tracking, Profit and loss by branch"
      },
      {
        "illustration": "portal",
        "title": "The resident's own portal",
        "text": "Most PG software stops at the owner. Every resident here gets a login, so they stop messaging you at eleven at night.",
        "points": "See rent and download receipts, Raise and follow complaints, Book laundry and see the food menu, Give checkout notice, Mark attendance at the gate, Read announcements"
      },
      {
        "illustration": "map",
        "title": "Filling empty beds",
        "text": "A public listing with photos and a real map. People searching nearby find you and enquire directly. No broker and no commission.",
        "points": "Up to six photos per branch, Search by pin, area or current location, Free beds shown as a band, never an exact count, Enquiries land in your inbox, Resident details never published"
      },
      {
        "illustration": "roles",
        "title": "Staff, roles and control",
        "text": "A manager, a warden and an accountant should not see the same screens. Build the roles you actually have rather than the three somebody assumed.",
        "points": "Custom roles with per-module permissions, Branch-scoped access, Staff records and salaries, Visitors and gate passes, QR gate attendance, Full audit log"
      }
    ]
  },
  "pricing_compare": {
    "title": "What each plan includes",
    "rows": [
      {
        "label": "Branches",
        "starter": "1",
        "professional": "3",
        "business": "10",
        "enterprise": "50"
      },
      {
        "label": "Beds",
        "starter": "60",
        "professional": "300",
        "business": "1,200",
        "enterprise": "8,000"
      },
      {
        "label": "Staff logins",
        "starter": "5",
        "professional": "20",
        "business": "75",
        "enterprise": "400"
      },
      {
        "label": "Resident portal",
        "starter": "yes",
        "professional": "yes",
        "business": "yes",
        "enterprise": "yes"
      },
      {
        "label": "Public listing and enquiries",
        "starter": "yes",
        "professional": "yes",
        "business": "yes",
        "enterprise": "yes"
      },
      {
        "label": "Rent, invoices and receipts",
        "starter": "yes",
        "professional": "yes",
        "business": "yes",
        "enterprise": "yes"
      },
      {
        "label": "Custom roles",
        "starter": "",
        "professional": "yes",
        "business": "yes",
        "enterprise": "yes"
      },
      {
        "label": "QR gate attendance",
        "starter": "",
        "professional": "yes",
        "business": "yes",
        "enterprise": "yes"
      },
      {
        "label": "Food and laundry",
        "starter": "",
        "professional": "yes",
        "business": "yes",
        "enterprise": "yes"
      },
      {
        "label": "Assets and inventory",
        "starter": "",
        "professional": "",
        "business": "yes",
        "enterprise": "yes"
      },
      {
        "label": "Audit log export",
        "starter": "",
        "professional": "",
        "business": "yes",
        "enterprise": "yes"
      },
      {
        "label": "API access",
        "starter": "",
        "professional": "",
        "business": "",
        "enterprise": "yes"
      },
      {
        "label": "Support",
        "starter": "Email",
        "professional": "Email + phone",
        "business": "Priority",
        "enterprise": "Dedicated manager"
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
      },
      {
        "q": "How long does setting up take?",
        "a": "A single branch with a few rooms takes about fifteen minutes. Rooms can be created in bulk, so a 200-bed hostel is an evening rather than a week."
      },
      {
        "q": "Do I have to publish my PG publicly?",
        "a": "No. Public listing is off until you switch it on, branch by branch. Nothing about your property is visible until you decide it should be."
      },
      {
        "q": "What do my tenants see about each other?",
        "a": "Nothing. A resident sees only their own rent, complaints and bookings. The public listing never shows resident details either."
      },
      {
        "q": "Can staff be limited to one branch?",
        "a": "Yes. Roles carry per-module permissions and staff can be scoped to the branches they actually work at."
      }
    ]
  },
  "cta": {
    "headline": "Start with one branch.",
    "text": "Set up your rooms and beds, add a few residents, and see a month through. Nothing to install.",
    "primary_label": "Create your account",
    "primary_href": "/signup",
    "secondary_label": "Download for Android",
    "secondary_href": "/pgguru.apk"
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
    "social_image_slot": "logo",
    "locale": "en_IN"
  }
}

export const SITE_PRESET_IMAGES = {
  "logo": {
    "slot": "logo",
    "src": "/pgguru-logo.png",
    "alt_text": "PGuru",
    "preset": true
  }
}
