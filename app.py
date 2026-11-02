import streamlit as st
from google import genai
import json
import re
import sqlite3
import uuid
from datetime import datetime
import pandas as pd
import fitz

# ----------------------------------
# PAGE CONFIGURATION
# ----------------------------------
st.set_page_config(
    page_title="LearnLoop AI",
    page_icon="🎓",
    layout="wide"
)

# ----------------------------------
# DATABASE: PERMANENT QUIZ HISTORY
# ----------------------------------
def init_database():
    conn = sqlite3.connect("learnloop.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            subject TEXT,
            topic TEXT,
            difficulty TEXT,
            score INTEGER,
            total_questions INTEGER,
            completed_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_quiz_result(name, subject, topic, level, score, total_questions=5):
    conn = sqlite3.connect("learnloop.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO quiz_history (
            student_name, subject, topic, difficulty,
            score, total_questions, completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        subject,
        topic,
        level,
        score,
        total_questions,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def get_quiz_history():
    conn = sqlite3.connect("learnloop.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT student_name, subject, topic, difficulty,
               score, total_questions, completed_at
        FROM quiz_history
        ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    conn.close()
    return rows


init_database()

# ----------------------------------
# APP HEADER AND GEMINI CONNECTION
# ----------------------------------
st.title("🎓 LearnLoop AI")
st.subheader("Your Personal AI Learning Assistant")

st.write(
    "Learn smarter with personalized explanations, "
    "AI-generated quizzes, and learning feedback."
)

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
except Exception:
    st.error("Gemini is not configured. Check your API key in .streamlit/secrets.toml.")
    st.stop()

st.success("🤖 AI assistant is ready!")
st.markdown("---")

# ----------------------------------
# STUDENT DETAILS
# ----------------------------------
name = st.text_input("What should we call you?")

subject = st.selectbox(
    "Choose a subject",
    [
        "Python Programming",
        "SQL and Databases",
        "Data Analytics",
        "Machine Learning",
        "Computer Networks"
    ]
)

topic = st.text_input(
    "What topic do you want to learn?",
    placeholder="Example: Python loops"
)

level = st.selectbox(
    "Choose your learning level",
    ["Beginner", "Intermediate", "Advanced"]
)

tab1, tab2, tab3 = st.tabs([
    "📘 Learn a Topic",
    "📝 Practice Quiz",
    "Progress Dashboard"
])

# ----------------------------------
# FEATURE 1: AI EXPLANATIONS + PDF
# ----------------------------------
with tab1:
    st.subheader("Understand Any Topic")
    st.markdown("### 📄 Learn from Your PDF")

    uploaded_pdf = st.file_uploader(
        "Upload your study notes or textbook",
        type=["pdf"],
        key="study_pdf"
    )

    if uploaded_pdf is not None:
        try:
            pdf_document = fitz.open(
                stream=uploaded_pdf.getvalue(),
                filetype="pdf"
            )

            pdf_text = "\n".join(
                page.get_text() for page in pdf_document
            )

            if pdf_text.strip():
                st.success("✅ PDF uploaded and text extracted successfully!")
                st.write("**Preview of your study material:**")
                st.text_area(
                    "Extracted PDF text",
                    pdf_text[:3000],
                    height=200
                )

                if st.button("🤖 Explain My PDF"):
                    with st.spinner("AI is reading your study material..."):
                        try:
                            response = client.models.generate_content(
                                model="gemini-3.5-flash-lite",
                                contents=f"""
                                Explain this study material in simple language.
                                Include:
                                1. Main concepts
                                2. Simple explanations
                                3. Practical examples
                                4. Important exam points
                                5. A short summary

                                Study material:
                                {pdf_text[:12000]}
                                """
                            )
                            st.markdown("### 📘 AI Explanation")
                            st.markdown(response.text)
                        except Exception as error:
                            st.error(f"AI explanation failed: {error}")

                # Generate a new PDF quiz
                if st.button("📝 Generate Quiz From PDF"):
                    with st.spinner("Generating questions from your PDF..."):
                        try:
                            quiz_prompt = f"""
                            Create exactly 5 multiple-choice questions based ONLY
                            on the study material below.

                            Return valid JSON in this format:
                            {{
                                "questions": [
                                    {{
                                        "question": "Question text",
                                        "options": {{
                                            "A": "Option A",
                                            "B": "Option B",
                                            "C": "Option C",
                                            "D": "Option D"
                                        }},
                                        "answer": "A",
                                        "explanation": "Explanation"
                                    }}
                                ]
                            }}

                            Study material:
                            {pdf_text[:12000]}
                            """

                            quiz_response = client.models.generate_content(
                                model="gemini-3.5-flash-lite",
                                contents=quiz_prompt
                            )

                            quiz_text = quiz_response.text.strip()
                            quiz_text = re.sub(
                                r"^```(?:json)?\s*|\s*```$",
                                "",
                                quiz_text
                            )

                            pdf_quiz = json.loads(quiz_text)

                            if (
                                not isinstance(pdf_quiz, dict)
                                or "questions" not in pdf_quiz
                                or len(pdf_quiz["questions"]) != 5
                            ):
                                raise ValueError(
                                    "The AI did not return exactly five questions."
                                )

                            for question in pdf_quiz["questions"]:
                                if (
                                    not all(
                                        key in question
                                        for key in [
                                            "question",
                                            "options",
                                            "answer",
                                            "explanation"
                                        ]
                                    )
                                    or len(question["options"]) != 4
                                    or question["answer"] not in question["options"]
                                ):
                                    raise ValueError(
                                        "The AI returned an invalid question."
                                    )

                            st.session_state["pdf_quiz"] = pdf_quiz
                            st.session_state["pdf_quiz_submitted"] = False
                            st.session_state["pdf_quiz_result"] = None
                            st.session_state["pdf_quiz_id"] = str(uuid.uuid4())
                            st.session_state["pdf_quiz_filename"] = uploaded_pdf.name

                            st.success("Quiz generated successfully!")

                        except Exception as error:
                            st.error(f"Quiz generation failed: {error}")

                # Display the generated PDF quiz
                if st.session_state.get("pdf_quiz"):
                    st.markdown("### 📝 Quiz Based on Your PDF")

                    questions = st.session_state["pdf_quiz"]["questions"]
                    quiz_id = st.session_state.get("pdf_quiz_id", "default")

                    if not st.session_state.get("pdf_quiz_submitted", False):
                        with st.form(f"pdf_quiz_form_{quiz_id}"):
                            selected_answers = {}

                            for i, question in enumerate(questions):
                                st.markdown(
                                    f"**Q{i + 1}. {question['question']}**"
                                )

                                options = question["options"]

                                selected_answers[i] = st.radio(
                                    f"Choose your answer for Question {i + 1}",
                                    options=list(options.keys()),
                                    index=None,
                                    format_func=lambda key, opts=options: (
                                        f"{key}. {opts[key]}"
                                    ),
                                    key=f"pdf_quiz_answer_{quiz_id}_{i}"
                                )

                            submitted = st.form_submit_button("🎯 Submit Quiz")

                        if submitted:
                            if any(
                                answer is None
                                for answer in selected_answers.values()
                            ):
                                st.warning(
                                    "Please answer all the questions before submitting!"
                                )
                            else:
                                score = sum(
                                    selected_answers[i] == question["answer"]
                                    for i, question in enumerate(questions)
                                )

                                # Save this PDF quiz result once
                                save_quiz_result(
                                    name.strip() or "Learner",
                                    "PDF Study Material",
                                    st.session_state.get(
                                        "pdf_quiz_filename",
                                        uploaded_pdf.name
                                    ),
                                    level,
                                    score,
                                    len(questions)
                                )

                                st.session_state["pdf_quiz_submitted"] = True
                                st.session_state["pdf_quiz_result"] = {
                                    "score": score,
                                    "answers": selected_answers
                                }
                                st.rerun()

                    # Keep results visible after submission and prevent resaving
                    if st.session_state.get("pdf_quiz_submitted", False):
                        result = st.session_state.get("pdf_quiz_result")

                        if result:
                            score = result["score"]
                            saved_answers = result["answers"]

                            st.success(
                                "✅ PDF quiz result saved to your Progress Dashboard!"
                            )
                            st.markdown("## 📊 Your Results")
                            st.success(
                                f"Your score: {score}/{len(questions)}"
                            )

                            for i, question in enumerate(questions):
                                correct_answer = question["answer"]
                                user_answer = saved_answers[i]

                                if user_answer == correct_answer:
                                    st.markdown(
                                        f"✅ **Question {i + 1}: Correct!**"
                                    )
                                else:
                                    st.markdown(
                                        f"❌ **Question {i + 1}: Incorrect.** "
                                        f"Correct answer: {correct_answer}. "
                                        f"{question['options'][correct_answer]}"
                                    )

                                st.info(
                                    f"Explanation: {question['explanation']}"
                                )

            else:
                st.warning(
                    "No readable text found. This PDF may contain scanned images."
                )

        except Exception as error:
            st.error(f"Unable to read this PDF. Please try another file. Details: {error}")

    # General topic explanation
    if st.button("✨ Explain This Topic"):
        if not name.strip() or not topic.strip():
            st.warning("Please enter your name and topic.")
        else:
            prompt = f"""
            You are LearnLoop AI, a friendly personal tutor.

            Student: {name}
            Subject: {subject}
            Topic: {topic}
            Level: {level}

            Explain this topic in simple language.
            Include:
            1. A clear explanation
            2. A practical example
            3. Common mistakes
            4. A short summary
            Adapt the explanation to the student's level.
            """

            with st.spinner("Preparing your explanation..."):
                try:
                    response = client.models.generate_content(
                        model="gemini-3.5-flash-lite",
                        contents=prompt
                    )
                    st.markdown("### 📚 Your Explanation")
                    st.markdown(response.text)
                except Exception as error:
                    st.error("Could not generate the explanation.")
                    st.code(str(error))

# ----------------------------------
# FEATURE 2: AI QUIZ GENERATOR
# ----------------------------------
with tab2:
    st.subheader("Test Your Understanding")
    st.write(
        "Generate five multiple-choice questions "
        "based on your selected subject and topic."
    )

    if st.button("🎯 Generate My Quiz"):
        if not name.strip() or not topic.strip():
            st.warning("Please enter your name and topic.")
        else:
            prompt = f"""
            Create exactly 5 educational multiple-choice questions.

            Subject: {subject}
            Topic: {topic}
            Difficulty: {level}

            Return ONLY a valid JSON array.
            Do not use markdown fences.

            Each array item must have:
            "question": a question,
            "options": exactly 4 answer choices,
            "answer": the exact correct option text,
            "explanation": a short explanation of the answer.

            Example format:
            [
              {{
                "question": "Example question?",
                "options": [
                  "Option A",
                  "Option B",
                  "Option C",
                  "Option D"
                ],
                "answer": "Option A",
                "explanation": "Why Option A is correct."
              }}
            ]

            Ensure every answer matches one of its options.
            """

            with st.spinner("Creating your personalized quiz..."):
                try:
                    response = client.models.generate_content(
                        model="gemini-3.5-flash-lite",
                        contents=prompt
                    )

                    raw_text = response.text.strip()
                    raw_text = re.sub(
                        r"^```(?:json)?\s*|\s*```$",
                        "",
                        raw_text
                    )

                    questions = json.loads(raw_text)

                    if not isinstance(questions, list) or len(questions) != 5:
                        raise ValueError(
                            "The AI did not return exactly five questions."
                        )

                    for question in questions:
                        if not all(
                            key in question
                            for key in [
                                "question",
                                "options",
                                "answer",
                                "explanation"
                            ]
                        ):
                            raise ValueError(
                                "A question is missing required information."
                            )

                        if (
                            len(question["options"]) != 4
                            or question["answer"] not in question["options"]
                        ):
                            raise ValueError(
                                "A question has invalid answer options."
                            )

                    st.session_state["quiz_questions"] = questions
                    st.session_state["quiz_topic"] = topic
                    st.session_state["quiz_student"] = name
                    st.session_state["quiz_submitted"] = False
                    st.session_state.pop("quiz_score", None)
                    st.session_state.pop("quiz_answers", None)

                except Exception as error:
                    st.error("Unable to create the quiz.")
                    st.code(str(error))

    # Display the generated general quiz
    questions = st.session_state.get("quiz_questions")

    if questions:
        st.markdown(
            f"### 📝 Quiz: {st.session_state['quiz_topic']}"
        )
        st.caption(
            f"Prepared for {st.session_state['quiz_student']}"
        )

        if not st.session_state.get("quiz_submitted", False):
            with st.form("quiz_form"):
                answers = []

                for i, question in enumerate(questions):
                    st.markdown(
                        f"**Question {i + 1}: {question['question']}**"
                    )

                    answer = st.radio(
                        f"Choose your answer for question {i + 1}",
                        question["options"],
                        index=None,
                        key=f"quiz_answer_{i}",
                        label_visibility="collapsed"
                    )

                    answers.append(answer)
                    st.markdown("---")

                submitted = st.form_submit_button("✅ Submit Quiz")

            if submitted:
                unanswered = [
                    i + 1
                    for i, answer in enumerate(answers)
                    if answer is None
                ]

                if unanswered:
                    st.warning(
                        "Please answer all questions before submitting. "
                        f"Unanswered: {', '.join(map(str, unanswered))}"
                    )
                else:
                    score = sum(
                        answer == question["answer"]
                        for answer, question in zip(answers, questions)
                    )

                    save_quiz_result(
                        st.session_state["quiz_student"],
                        subject,
                        st.session_state["quiz_topic"],
                        level,
                        score,
                        len(questions)
                    )

                    st.session_state["quiz_submitted"] = True
                    st.session_state["quiz_score"] = score
                    st.session_state["quiz_answers"] = answers
                    st.rerun()

        if st.session_state.get("quiz_submitted", False):
            score = st.session_state["quiz_score"]
            answers = st.session_state["quiz_answers"]

            st.markdown("---")
            st.subheader("🏆 Your Quiz Results")
            st.metric("Your Score", f"{score} / 5")
            st.progress(score / 5)

            if score == 5:
                st.success("Excellent! You answered every question correctly!")
            elif score >= 3:
                st.success("Good work! Review the questions you missed.")
            else:
                st.info(
                    "Keep practising! Review the explanations below "
                    "and try another quiz."
                )

            st.subheader("📖 Answer Review")

            for i, question in enumerate(questions):
                correct = answers[i] == question["answer"]

                if correct:
                    st.success(f"Question {i + 1}: Correct!")
                else:
                    st.error(f"Question {i + 1}: Incorrect")

                st.write(f"Your answer: {answers[i]}")
                st.write(f"Correct answer: {question['answer']}")
                st.write(f"Explanation: {question['explanation']}")
                st.markdown("---")

            if st.button("🔄 Generate Another Quiz"):
                for key in [
                    "quiz_questions",
                    "quiz_submitted",
                    "quiz_score",
                    "quiz_answers",
                    "quiz_topic",
                    "quiz_student"
                ]:
                    st.session_state.pop(key, None)
                st.rerun()

# ----------------------------------
# FEATURE 3: PROGRESS DASHBOARD
# ----------------------------------
with tab3:
    st.subheader("📊 Your Learning Progress")

    history = get_quiz_history()

    if not history:
        st.info("Complete your first quiz to see your progress!")
    else:
        df = pd.DataFrame(
            history,
            columns=[
                "Student",
                "Subject",
                "Topic",
                "Difficulty",
                "Score",
                "Total Questions",
                "Completed At"
            ]
        )

        df["Score (%)"] = (
            df["Score"] / df["Total Questions"] * 100
        )

        col1, col2, col3 = st.columns(3)

        col1.metric("Quizzes Completed", len(df))
        col2.metric("Average Score", f"{df['Score (%)'].mean():.1f}%")
        col3.metric("Best Score", f"{df['Score (%)'].max():.1f}%")

        st.subheader("📈 Quiz Performance")

        chart_df = df.iloc[::-1].copy()
        chart_df["Attempt"] = range(1, len(chart_df) + 1)

        st.line_chart(
            chart_df.set_index("Attempt")["Score (%)"],
            y_label="Score (%)",
            x_label="Quiz Attempt",
            height=350
        )

        st.subheader("📚 Quiz History")

        st.dataframe(
            df[
                [
                    "Student",
                    "Subject",
                    "Topic",
                    "Difficulty",
                    "Score",
                    "Total Questions",
                    "Score (%)",
                    "Completed At"
                ]
            ],
            use_container_width=True
        )

st.markdown("---")
st.caption("LearnLoop AI | Personalized learning powered by Gemini")