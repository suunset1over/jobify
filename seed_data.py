#!/usr/bin/env python3
# seed_data.py
# Run this once to bulk-insert your Articles and News entries.

from app import app
from extensions import db
from models.article import Article
from models.news import News
from datetime import datetime

def run():
    with app.app_context():
        # ─── ARTICLES ─────────────────────────────────────────────────────────────
        a = Article(
            title="Mastering the Art of Job Interviews",
            teaser="Ace your next interview with these expert-backed tips.",
            body=(
                "Job interviews can feel intimidating, but with proper preparation you can stand out from the competition.\n"
                "Here are 5 expert-backed strategies to help you succeed:\n\n"
                "1️⃣ Research the Company  \n"
                "   Understand their mission, products, services, and culture. Use this knowledge to personalize your answers.\n\n"
                "2️⃣ Practice Common Interview Questions  \n"
                "   Prepare answers for frequently asked questions like:\n"
                "   - \"Tell me about yourself\"\n"
                "   - \"What are your strengths and weaknesses?\"\n"
                "   - \"Why do you want this job?\"\n\n"
                "3️⃣ Showcase Your Achievements  \n"
                "   Use specific examples and measurable results to highlight your impact in previous roles.\n\n"
                "4️⃣ Ask Thoughtful Questions  \n"
                "   Demonstrate genuine interest by asking questions about team dynamics, growth opportunities, and company vision.\n\n"
                "5️⃣ Follow Up  \n"
                "   Send a personalized thank-you email to your interviewers to reinforce your interest and professionalism.\n\n"
                "💡 Remember: Confidence comes from preparation. Believe in your skills, and let your passion shine through!"
            ),
            image_url="/static/img/job_interview_tips.png",
            created_at=datetime.utcnow()
        )

        a1 = Article(
            title="Quiz: How Friendly Are You at Work?",
            teaser="Take a short test and discover your office-friend type.",
            body=(
                "If you’ve ever worked on a team, you know the value of a reliable 'work bestie.'  \n"
                "Take this quick quiz to see what kind of office-friend you are!\n\n"
                "1. You and your bestie are like…\n"
                "   A. 'Coffee & donuts' — 4 points\n"
                "   B. 'Never-ending chats' — 3 points\n"
                "   C. 'Meme squad' — 2 points\n"
                "   D. 'Quiet backbone' — 1 point\n\n"
                "2. How often do you message your coworker about non-work stuff?\n"
                "   A. Daily (memes, videos, horoscopes) — 4 points\n"
                "   B. Save all the memes for them — 3 points\n"
                "   C. Only if it really resonates — 2 points\n"
                "   D. Rarely, but perfectly timed — 1 point\n\n"
                "3. Imagine you’re in a morning stand-up. What mood are you in?\n"
                "   A. Pumped—they’ve saved me a seat! — 4 points\n"
                "   B. Positive—and we’ll catch up after — 3 points\n"
                "   C. Tired—duck to the back — 2 points\n"
                "   D. Need to login remotely — 1 point\n\n"
                "4. At a company party themed 'Movie characters,' what do you wear?\n"
                "   A. Iconic duo because of our inside jokes — 4 points\n"
                "   B. Brothers from that indie film — 3 points\n"
                "   C. American prom heroes — 2 points\n"
                "   D. Favorite new show character — 1 point\n\n"
                "**Scoring & Results**\n"
                "- 4–7 points: Quiet Support — you’re the calm rock of your team.\n"
                "- 8–11 points: Energizer Buddy — you keep spirits high and chatter flowing.\n"
                "- 12–15 points: Meme Master — your humor is the glue that bonds everyone.\n"
                "- 16 points: Ultimate Bestie — you’re both heart and hype for your coworkers!\n\n"
                "A well-crafted resume isn’t just a formality—it’s your first conversation with an employer. Make it count."
            ),
            image_url="/static/img/quiz_banner.png",
            created_at=datetime.utcnow()
        )

        a2 = Article(
            title="Quiz: What Will a Recruiter Say About Your Resume?",
            teaser="See what impression your CV makes on a recruiter—and get tips to strengthen it.",
            body=(
                "A resume is your business card—it should convey the essence of your professional experience at first glance. "
                "In a world where dozens or even hundreds of candidates apply for one job, the recruiter has only a few seconds "
                "to decide: keep reading or close it.\n\n"
                "Jobify.ro has created this quiz to help you look at your own resume through the eyes of a recruiter. It will "
                "show how clear, logical, and professional your CV is, and provide suggestions on what to improve.\n\n"
                "**Instructions:** Choose the option that best describes your resume. Count your points and find out your result.\n\n"
                "1) What is the title of your resume?\n"
                "   A. The job position I want to apply for (3 points)\n"
                "   B. All the job positions I could potentially apply for (2 points)\n"
                "   C. Factory worker (1 point)\n"
                "   D. Ready for any job (0 points)\n\n"
                "2) What does the header of your resume look like?\n"
                "   A. Name, contact info, LinkedIn — everything in place (3 points)\n"
                "   B. Name and phone number, but no email (or vice versa) (2 points)\n"
                "   C. Just 'Ann, 26 years old' (1 point)\n"
                "   D. Header? Like a cap? (0 points)\n\n"
                # … continue each question …
                "\nA well-crafted resume isn’t just a formality—it’s your first conversation with an employer. Make it count."
            ),
            image_url="/static/img/recruiter_say.png",
            created_at=datetime.utcnow()
        )

        # ─── NEWS ────────────────────────────────────────────────────────────────
        n = News(
            title="🇷🇴 Romania: Largest Employers by Region (2024–2025)",
            teaser="A regional breakdown of Romania’s top employers, from Bucharest to Dobrogea.",
            body=(
                "1. **Bucharest–Ilfov (Capital Region)**\n"
                "   • Metro România – over 4,000 employees in the Cash & Carry network.\n"
                "   • Auchan Retail România – approximately 440 stores with a large workforce.\n"
                "   • NN Romania, EY Romania, Microsoft, Google, Continental, Oracle, Bosch, Amazon, ING Bank, IBM, HP.\n\n"
                "2. **North–East (Iași Region)**\n"
                "   • “Al. I. Cuza” University & “Gh. Asachi” Technical University – 2,000+ employees each.\n"
                "   • Sfântul Spiridon Hospital – around 2,944 employees.\n"
                "   • BorgWarner, Continental Automotive, Amazon Dev Center, Antibiotice Iași, AlmavivA, CTP, ApaVital.\n\n"
                # … continue each region …
                "\n**Key Takeaways:**\n"
                "- IT & finance lead in Bucharest, Cluj, Timișoara, Iași.\n"
                "- Automotive & manufacturing drive Transylvania & West.\n"
                "- Retail & logistics chains span all regions.\n"
                "- Public institutions (CFR, Spiridon Hospital) remain major employers."
            ),
            image_url="/static/img/romania_employees.png",
            created_at=datetime.utcnow()
        )

        n2 = News(
            title="Jobify.ro Reaches 5,000 Active Listings",
            teaser="A major milestone for Romania's fastest-growing job platform.",
            body=(
                "We’re proud to announce that Jobify.ro now hosts over 5,000 active job vacancies across all Romanian regions. "
                "This achievement underscores the platform’s commitment to connecting talent with opportunity, offering "
                "intuitive search, real-time notifications, and personalized job recommendations to both candidates and recruiters.\n\n"
                "**Key highlights:**\n"
                "- Over 2,000 listings in IT & Tech roles\n"
                "- 1,200+ opportunities in Sales & Marketing\n"
                "- Rapidly expanding presence in Healthcare and Education sectors\n\n"
                "Thank you to our community of users for making this possible. Stay tuned for even more features and regional "
                "expansion plans in 2025."
            ),
            image_url="/static/img/news_5000_listings.png",
            created_at=datetime.utcnow()
        )

        db.session.add_all([a, a1, a2, n, n2])
        db.session.commit()
        print("✅ Seeded all Articles and News.")

if __name__ == "__main__":
    run()
