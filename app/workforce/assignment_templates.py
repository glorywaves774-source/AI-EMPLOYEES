"""Ready-made assignment starters. Text in [square brackets] is for the user to fill in."""

TEMPLATES = [
    {"key": "marketing-plan", "group": "Marketing", "label": "Monthly marketing plan",
     "title": "Marketing plan for [month]",
     "details": "Prepare a practical marketing plan for [month] for our business, [what we sell], aimed at [who our customers are] in [town/region].\n"
                "Our budget is about GHS [amount]. Include: the main goal, 4-6 activities with dates, which channels to use "
                "(e.g. WhatsApp, Facebook, radio, flyers), a budget table in GHS, and how we will measure results."},
    {"key": "social-posts", "group": "Marketing", "label": "A week of social media posts",
     "title": "Social media posts for the week of [date]",
     "details": "Write 7 social media posts (one a day) for [Facebook / Instagram / WhatsApp Status] promoting [product or offer].\n"
                "Tone: [friendly / professional]. For each post give the text (under 60 words), 3 hashtags and an idea for the picture. "
                "Include one post that answers a common customer question."},
    {"key": "complaint-reply", "group": "Customers", "label": "Reply to a customer complaint",
     "title": "Reply to a complaint about [issue]",
     "details": "A customer complained: \"[paste or describe the complaint]\".\nDraft a polite, empathetic reply that apologises "
                "where appropriate, explains what happened and what we will do next. Do not promise refunds or discounts. "
                "Also suggest one change that would stop this happening again."},
    {"key": "customer-faq", "group": "Customers", "label": "Customer FAQ",
     "title": "Frequently asked questions for [product/service]",
     "details": "Write 12 frequently asked questions and clear answers for customers of [product/service], covering prices, "
                "delivery or opening hours, payment methods (including Mobile Money), returns and how to contact us. "
                "Use only facts from our business documents and mark anything you are unsure of as [to confirm]."},
    {"key": "job-advert", "group": "People", "label": "Job advert and interview questions",
     "title": "Job advert: [job title]",
     "details": "We are hiring a [job title] in [location], [full-time/part-time], salary about GHS [amount] a month.\n"
                "Write the job advert (duties, requirements, how to apply, closing date [date]) and 10 interview questions "
                "with what a good answer looks like. Keep it fair and non-discriminatory."},
    {"key": "staff-policy", "group": "People", "label": "Staff policy",
     "title": "[Topic] policy for staff",
     "details": "Draft a clear staff policy on [topic, e.g. leave, lateness, use of phones, customer data] for a business with "
                "[number] staff. Include purpose, rules, steps to follow and consequences. Flag anything that needs a lawyer's check "
                "under Ghana's Labour Act."},
    {"key": "cash-flow", "group": "Finance", "label": "3-month cash-flow forecast",
     "title": "Cash-flow forecast for [months]",
     "details": "Prepare a 3-month cash-flow forecast in GHS. Expected monthly sales: about GHS [amount]. Main costs: rent GHS [amount], "
                "salaries GHS [amount], stock GHS [amount], other GHS [amount]. Show a table per month (money in, money out, balance), "
                "point out any month we might run short, and suggest three ways to improve cash flow."},
    {"key": "pricing", "group": "Finance", "label": "Price my product or service",
     "title": "Pricing for [product/service]",
     "details": "Help us set a price for [product/service]. Our cost per unit is about GHS [amount]; competitors charge about GHS [amount]. "
                "Show three price options with the profit margin for each in a table, the break-even number of sales per month, "
                "and which option you recommend and why."},
    {"key": "proposal", "group": "Sales", "label": "Proposal for a client",
     "title": "Proposal for [client name]",
     "details": "Write a short business proposal to [client name] for [what we will provide]. Include: their need, our solution, "
                "what is included, timeline, price in GHS [amount], why choose us, and next steps. Keep it to about 2 pages."},
    {"key": "competitors", "group": "Research", "label": "Competitor check",
     "title": "Competitor analysis for [our business]",
     "details": "Compare our business, [what we sell], with these competitors: [name 1], [name 2], [name 3]. Use a table to compare "
                "prices, products, strengths and weaknesses, then suggest 5 practical ways we can stand out. Say clearly where "
                "information is assumed rather than known."},
    {"key": "sop", "group": "Operations", "label": "Step-by-step procedure (SOP)",
     "title": "Standard operating procedure: [task]",
     "details": "Write a step-by-step procedure for [task, e.g. opening the shop, receiving stock, handling cash], for new staff. "
                "Include who does it, what they need, numbered steps, common mistakes and a short checklist."},
    {"key": "donor-report", "group": "NGOs & schools", "label": "Donor or board report",
     "title": "[Quarter] report for [donor/board]",
     "details": "Prepare a report for [donor/board] covering [period]. Activities: [list them]. Results: [numbers, e.g. people reached]. "
                "Spending: GHS [amount] of GHS [budget]. Include a summary, achievements, challenges, a spending table and plans for "
                "next quarter."},
]

BY_KEY = {t["key"]: t for t in TEMPLATES}
