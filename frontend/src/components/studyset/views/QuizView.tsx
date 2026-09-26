/** Port of python/quiz_launcher.py. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LibraryShell, DetailRow } from "../LibraryShell";
import { createQuizAttempt, listQuizAttempts, type QuizAttempt } from "../lib/api";
import { req, ValidationError } from "../lib/content";
import { shuffle } from "../lib/format";
import { useLibrary } from "../lib/useLibrary";
import { DIFFICULTIES, type Quiz, type QuizQuestion } from "../types";

function parseQuiz(raw: Record<string, unknown>, where: string): Quiz {
  const questions = req<unknown[]>(raw, "questions", "array", where);
  if (questions.length === 0) throw new ValidationError(`${where}: quiz contains no questions`);

  return {
    title: req<string>(raw, "title", "string", where),
    description: (raw.description as string) ?? "",
    questions: questions.map((entry, i) => {
      const q = entry as Record<string, unknown>;
      const at = `${where} question ${i + 1}`;
      const options = req<string[]>(q, "options", "array", at);
      const correct = req<number>(q, "correct", "number", at);
      if (options.length < 4 || options.length > 6) {
        throw new ValidationError(`${at}: expected 4-6 options, got ${options.length}`);
      }
      if (correct < 0 || correct >= options.length) {
        throw new ValidationError(`${at}: correct index ${correct} out of range`);
      }
      const difficulty = (q.difficulty as QuizQuestion["difficulty"]) ?? "understanding";
      if (!DIFFICULTIES.includes(difficulty)) {
        throw new ValidationError(`${at}: unknown difficulty '${difficulty}'`);
      }
      return {
        question: req<string>(q, "question", "string", at),
        options,
        correct,
        explanation: req<string>(q, "explanation", "string", at),
        difficulty,
        sources: (q.sources as string[]) ?? [],
      };
    }),
  };
}

/** Port of quiz_launcher.shuffled_copy. */
function prepare(quiz: Quiz, shuffleQuestions: boolean, shuffleOptions: boolean): Quiz {
  const questions = quiz.questions.map((q) => {
    if (!shuffleOptions) return { ...q, options: [...q.options] };
    const order = shuffle(q.options.map((_, i) => i));
    return {
      ...q,
      options: order.map((i) => q.options[i]),
      correct: order.indexOf(q.correct),
    };
  });
  return { ...quiz, questions: shuffleQuestions ? shuffle(questions) : questions };
}

export function QuizView() {
  const lib = useLibrary<Quiz>("quizzes", parseQuiz);
  const [shuffleOptions, setShuffleOptions] = useState(true);
  const [shuffleQuestions, setShuffleQuestions] = useState(false);
  const [run, setRun] = useState<Quiz | null>(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [choice, setChoice] = useState<number | null>(null);
  const [finished, setFinished] = useState(false);
  const [attempts, setAttempts] = useState<QuizAttempt[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const attemptSaved = useRef(false);

  const quiz = lib.selected?.doc ?? null;
  const selectedFile = lib.selected?.entry.file ?? null;

  const loadHistory = useCallback(async () => {
    if (!selectedFile) {
      setAttempts([]);
      return;
    }
    try {
      const result = await listQuizAttempts(selectedFile);
      setAttempts(result.attempts);
      setHistoryError(null);
    } catch (error) {
      setHistoryError((error as Error).message);
    }
  }, [selectedFile]);

  const start = useCallback(
    (quiz: Quiz) => {
      const prepared = prepare(quiz, shuffleQuestions, shuffleOptions);
      setRun(prepared);
      setIndex(0);
      setAnswers(new Array(prepared.questions.length).fill(null));
      setChoice(null);
      setFinished(false);
      setShowHistory(false);
      setHistoryError(null);
      attemptSaved.current = false;
    },
    [shuffleOptions, shuffleQuestions],
  );

  useEffect(() => {
    setRun(null);
    setFinished(false);
    setShowHistory(false);
    attemptSaved.current = false;
    void loadHistory();
  }, [lib.selectedIndex, lib.documents.length, loadHistory]);

  const score = useMemo(
    () =>
      run
        ? answers.reduce<number>(
            (total, answer, i) =>
              answer !== null && answer === run.questions[i].correct ? total + 1 : total,
            0,
          )
        : 0,
    [answers, run],
  );
  const answered = answers.filter((a) => a !== null).length;

  const submit = () => {
    if (choice === null || !run) return;
    const next = [...answers];
    next[index] = choice;
    setAnswers(next);
  };

  const goto = (target: number) => {
    if (!run || target < 0 || target >= run.questions.length) return;
    setIndex(target);
    setChoice(answers[target]);
  };

  const saveAttempt = useCallback(async () => {
    if (!run || !selectedFile || attemptSaved.current) return;
    attemptSaved.current = true;
    const responses = run.questions.map((question, questionIndex) => {
      const selected = answers[questionIndex];
      return {
        question: question.question,
        selectedAnswer: selected === null ? null : question.options[selected],
        correctAnswer: question.options[question.correct],
        correct: selected !== null && selected === question.correct,
        explanation: question.explanation,
      };
    });
    try {
      const attempt = await createQuizAttempt(
        selectedFile,
        run.title,
        responses,
        score,
        run.questions.length,
      );
      setAttempts((current) => [attempt, ...current.filter((item) => item.id !== attempt.id)]);
      setHistoryError(null);
    } catch (error) {
      attemptSaved.current = false;
      setHistoryError(`Could not save quiz history: ${(error as Error).message}`);
    }
  }, [answers, run, score, selectedFile]);

  const next = () => {
    if (!run) return;
    if (index < run.questions.length - 1) goto(index + 1);
    else {
      setFinished(true);
      void saveAttempt();
    }
  };

  const details = quiz ? (
    <>
      <p className="details-title">{quiz.title}</p>
      <p className="muted small">{quiz.description}</p>
      <DetailRow label="Questions" value={quiz.questions.length} />
      <DetailRow
        label="Difficulty mix"
        value={DIFFICULTIES.filter((d) => quiz.questions.some((q) => q.difficulty === d))
          .map((d) => `${d}: ${quiz.questions.filter((q) => q.difficulty === d).length}`)
          .join(", ")}
      />
      <DetailRow
        label="Sources"
        value={[...new Set(quiz.questions.flatMap((q) => q.sources))].join(", ") || "n/a"}
      />
      <DetailRow label="File" value={lib.selected?.entry.file ?? "n/a"} />
    </>
  ) : null;

  const toolbar = (
    <>
      <button type="button" onClick={lib.reload}>
        Reload
      </button>
      <span className="divider" />
      <label className="check">
        <input
          type="checkbox"
          checked={shuffleOptions}
          onChange={(e) => setShuffleOptions(e.target.checked)}
        />
        Shuffle answer options
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={shuffleQuestions}
          onChange={(e) => setShuffleQuestions(e.target.checked)}
        />
        Shuffle question order
      </label>
      <span className="spacer" />
      <button
        type="button"
        disabled={!quiz}
        onClick={() => {
          setShowHistory((value) => !value);
          void loadHistory();
        }}
      >
        {showHistory ? "Back to quiz" : `History (${attempts.length})`}
      </button>
      <button type="button" className="primary" disabled={!quiz} onClick={() => quiz && start(quiz)}>
        {run ? "Restart quiz" : "Start quiz"}
      </button>
    </>
  );

  let body: React.ReactNode;
  if (!quiz) {
    body = <div className="placeholder">Select a quiz.</div>;
  } else if (showHistory) {
    body = (
      <div className="scroll pad">
        <h2>Quiz history</h2>
        <p className="muted">Saved attempts for {quiz.title}</p>
        {historyError ? <p className="bad" role="alert">{historyError}</p> : null}
        {attempts.length === 0 ? <p className="muted">No saved attempts yet.</p> : null}
        {attempts.map((attempt) => (
          <section className="review" key={attempt.id}>
            <h3>{attempt.score} / {attempt.total}</h3>
            <p className="muted small">{new Date(attempt.completedAt).toLocaleString()}</p>
            {attempt.responses.map((response, responseIndex) => (
              <div key={responseIndex}>
                <p><strong>{responseIndex + 1}. {response.question}</strong></p>
                <p className={response.correct ? "ok" : "bad"}>
                  Your answer: {response.selectedAnswer ?? "(no answer)"}
                </p>
                {!response.correct ? <p className="ok">Correct answer: {response.correctAnswer}</p> : null}
              </div>
            ))}
          </section>
        ))}
      </div>
    );
  } else if (!run) {
    body = (
      <div className="placeholder">
        <h2>{quiz.title}</h2>
        <p className="muted">{quiz.description}</p>
        <button type="button" className="primary big" onClick={() => start(quiz)}>
          Start quiz
        </button>
      </div>
    );
  } else if (finished) {
    const total = run.questions.length;
    const pct = Math.round((score / total) * 100);
    const verdict =
      pct >= 90
        ? "Excellent — you have mastered this material."
        : pct >= 70
          ? "Good work — a solid understanding of the text."
          : pct >= 50
            ? "A reasonable start; review the explanations below."
            : "Worth another pass through the source text before retrying.";
    body = (
      <div className="scroll pad">
        <h2>Quiz results</h2>
        <p className="big-score">
          {score} / {total} <span className="muted">({pct}%)</span>
        </p>
        <p className="muted">{verdict}</p>
        {historyError ? (
          <p className="bad" role="alert">
            {historyError} <button type="button" onClick={() => void saveAttempt()}>Retry save</button>
          </p>
        ) : null}
        <div className="row gap">
          <button type="button" className="primary" onClick={() => start(quiz)}>
            Retake quiz
          </button>
        </div>
        <hr />
        {run.questions.map((q, i) => {
          const given = answers[i];
          const ok = given !== null && given === q.correct;
          return (
            <section key={i} className="review">
              <h3>
                {i + 1}. {q.question}
              </h3>
              <p className={ok ? "ok" : "bad"}>
                Your answer ({ok ? "correct" : "incorrect"}):{" "}
                {given === null ? "(no answer)" : q.options[given]}
              </p>
              {!ok && <p className="ok">Correct answer: {q.options[q.correct]}</p>}
              <p className="muted">{q.explanation}</p>
              {q.sources.length > 0 && (
                <p className="muted small">Source: {q.sources.join(", ")}</p>
              )}
            </section>
          );
        })}
      </div>
    );
  } else {
    const q = run.questions[index];
    const given = answers[index];
    const locked = given !== null;
    body = (
      <div className="scroll pad">
        <div className="row between">
          <strong>
            Question {index + 1} of {run.questions.length}
          </strong>
          <span className="muted">Difficulty: {q.difficulty}</span>
        </div>
        <progress value={answered} max={run.questions.length} />
        <h2 className="question">{q.question}</h2>

        <fieldset className="options" disabled={locked}>
          <legend className="visually-hidden">Choose one</legend>
          {q.options.map((option, i) => (
            <label key={i} className={locked && i === q.correct ? "option correct" : "option"}>
              <input
                type="radio"
                name={`q-${index}`}
                checked={(locked ? given : choice) === i}
                onChange={() => setChoice(i)}
              />
              <span>
                {i + 1}. {option}
              </span>
            </label>
          ))}
        </fieldset>

        {locked && (
          <div className={given === q.correct ? "feedback ok" : "feedback bad"}>
            <strong>
              {given === q.correct
                ? "Correct."
                : `Incorrect. The answer is: ${q.options[q.correct]}`}
            </strong>
            <p>{q.explanation}</p>
            {q.sources.length > 0 && (
              <p className="muted small">Source: {q.sources.join(", ")}</p>
            )}
          </div>
        )}

        <div className="row gap">
          <button type="button" onClick={() => goto(index - 1)} disabled={index === 0}>
            ← Previous
          </button>
          <button type="button" className="primary" onClick={submit} disabled={locked || choice === null}>
            Submit answer
          </button>
          <button type="button" onClick={next}>
            {index === run.questions.length - 1 ? "Finish ✓" : "Next →"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <LibraryShell
      documents={lib.documents}
      errors={lib.errors}
      loading={lib.loading}
      selectedIndex={lib.selectedIndex}
      onSelect={lib.select}
      titleOf={(q) => q.title}
      details={details}
      toolbar={toolbar}
      status={run ? `Score: ${score}/${answered}` : `${lib.documents.length} quizzes`}
      hint="Select an answer, submit, then advance"
      emptyMessage="No quizzes found in new_output/*/quizzes."
    >
      {body}
    </LibraryShell>
  );
}
