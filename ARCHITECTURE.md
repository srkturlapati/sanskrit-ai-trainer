# Sanskrit Language Proficiency Test (SLPT) Architecture

## System architecture

```text
Browser (Next.js + Tailwind + Noto Sans Devanagari)
  ├─ Candidate dashboard: timer, autosave, accessibility, Devanagari/IAST input
  ├─ MediaRecorder / Web Audio API ── signed upload ──> S3-compatible object storage
  └─ HTTPS REST/JSON ─────────────────────────────────> API (FastAPI or Express)
                                                          ├─ PostgreSQL
                                                          ├─ Redis: sessions, rate limits, job queue
                                                          ├─ Worker: auto-grade Reading/Listening
                                                          └─ Worker: AI evaluation
                                                               ├─ speech transcription/pronunciation
                                                               └─ writing rubric evaluation
Admin CMS ────────────────────────────────────────────> API: templates, items, assets, review queue
```

**Recommended production boundaries.** Keep answer keys, scoring logic, signed-upload generation, and test-attempt state server-side. The browser receives only delivery-safe question data. A worker processes AI tasks asynchronously and a reviewer can override a score; publish an immutable score revision rather than overwriting the original.

## PostgreSQL schema

```sql
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TYPE test_status AS ENUM ('not_started','in_progress','submitted','scoring','completed','void');
CREATE TYPE section_type AS ENUM ('reading','listening','speaking','writing');
CREATE TYPE score_status AS ENUM ('pending','provisional','review_required','final');

CREATE TABLE users (
  id UUID PRIMARY KEY, email CITEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'candidate' CHECK (role IN ('candidate','author','reviewer','admin')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE test_templates (
  id UUID PRIMARY KEY, code TEXT UNIQUE NOT NULL, title TEXT NOT NULL, version INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','published','retired')), duration_seconds INTEGER NOT NULL,
  created_by UUID REFERENCES users(id), published_at TIMESTAMPTZ, UNIQUE(code, version)
);
CREATE TABLE template_sections (
  id UUID PRIMARY KEY, template_id UUID NOT NULL REFERENCES test_templates(id) ON DELETE CASCADE,
  section section_type NOT NULL, position SMALLINT NOT NULL, duration_seconds INTEGER NOT NULL,
  scaled_max SMALLINT NOT NULL DEFAULT 30, UNIQUE(template_id, section)
);
CREATE TABLE passages (
  id UUID PRIMARY KEY, devanagari TEXT, iast TEXT, translation TEXT,
  audio_object_key TEXT, transcript TEXT, attribution TEXT, CHECK (devanagari IS NOT NULL OR audio_object_key IS NOT NULL)
);
CREATE TABLE questions (
  id UUID PRIMARY KEY, section section_type NOT NULL, prompt_devanagari TEXT NOT NULL,
  prompt_iast TEXT, passage_id UUID REFERENCES passages(id), item_type TEXT NOT NULL,
  difficulty NUMERIC(4,2), scoring_key JSONB NOT NULL, rubric JSONB, status TEXT NOT NULL DEFAULT 'draft'
);
CREATE TABLE question_choices (
  id UUID PRIMARY KEY, question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  choice_key TEXT NOT NULL, content_devanagari TEXT NOT NULL, content_iast TEXT, position SMALLINT NOT NULL,
  is_correct BOOLEAN NOT NULL DEFAULT false, UNIQUE(question_id, choice_key)
);
CREATE TABLE template_questions (
  template_section_id UUID NOT NULL REFERENCES template_sections(id) ON DELETE CASCADE,
  question_id UUID NOT NULL REFERENCES questions(id), position SMALLINT NOT NULL,
  PRIMARY KEY(template_section_id, question_id), UNIQUE(template_section_id, position)
);
CREATE TABLE test_attempts (
  id UUID PRIMARY KEY, candidate_id UUID NOT NULL REFERENCES users(id), template_id UUID NOT NULL REFERENCES test_templates(id),
  status test_status NOT NULL DEFAULT 'not_started', started_at TIMESTAMPTZ, submitted_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ, accommodations JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE attempt_sections (
  id UUID PRIMARY KEY, attempt_id UUID NOT NULL REFERENCES test_attempts(id) ON DELETE CASCADE,
  section section_type NOT NULL, started_at TIMESTAMPTZ, submitted_at TIMESTAMPTZ, time_remaining_seconds INTEGER, UNIQUE(attempt_id, section)
);
CREATE TABLE responses (
  id UUID PRIMARY KEY, attempt_section_id UUID NOT NULL REFERENCES attempt_sections(id) ON DELETE CASCADE,
  question_id UUID NOT NULL REFERENCES questions(id), selected_choice_key TEXT, text_response TEXT,
  audio_object_key TEXT, submitted_at TIMESTAMPTZ, autosave_version INTEGER NOT NULL DEFAULT 0,
  UNIQUE(attempt_section_id, question_id)
);
CREATE TABLE section_scores (
  id UUID PRIMARY KEY, attempt_section_id UUID UNIQUE NOT NULL REFERENCES attempt_sections(id) ON DELETE CASCADE,
  raw_score NUMERIC(6,2), scaled_score NUMERIC(4,1) CHECK (scaled_score BETWEEN 0 AND 30),
  status score_status NOT NULL DEFAULT 'pending', rubric_evidence JSONB NOT NULL DEFAULT '{}',
  model_name TEXT, model_version TEXT, confidence NUMERIC(4,3), reviewer_id UUID REFERENCES users(id), finalized_at TIMESTAMPTZ
);
CREATE INDEX responses_section_question_idx ON responses(attempt_section_id, question_id);
CREATE INDEX test_attempts_candidate_status_idx ON test_attempts(candidate_id, status);
```

## Scoring and AI guidelines

1. **Auto-grade deterministically.** On section submission, validate the attempt clock and selected choice IDs, score Reading/Listening from server-only keys, and map raw scores through a versioned conversion table to 0–30.
2. **Use asynchronous AI scoring.** Store speaking audio in object storage through a short-lived, content-type-restricted upload URL. Queue transcription and writing evaluation, keeping the candidate-facing response provisional.
3. **Score against explicit rubrics.** Speaking dimensions: delivery/pronunciation, language use, topic development. Writing dimensions: task fulfilment, organization, grammar/syntax, vocabulary. Save dimensional values and excerpts/evidence in `rubric_evidence`.
4. **Retain humans in the loop.** Route low confidence, failed transcription, suspected mismatch, and accommodation cases to `review_required`. AI providers must not determine identity, cheating guilt, or permanent educational placement.
5. **Protect assessment integrity.** Encrypt audio at rest, issue private object keys, log all administrative answer-key access, rate-limit autosaves, enforce idempotency keys, and make a test template immutable after publication.

## Delivery roadmap

### MVP 1 — Assessment shell
- Build authentication, candidate profile, published-template delivery, accessible Reading split screen, server-authoritative timer, and autosave.
- Add question authoring for MCQs, randomized option order, deterministic Reading/Listening grading, result history, and audit logs.

### MVP 2 — Sanskrit-first media and input
- Add Noto Sans Devanagari, parallel Devanagari/IAST passage fields, system-IME guidance and on-screen keyboard component.
- Add signed audio playback/upload, Listening transcripts for approved accommodations, MediaRecorder speaking capture, retry-safe uploads, and object lifecycle rules.

### MVP 3 — AI-assisted evaluation
- Add queued transcription/evaluation workers, rubric schemas, evidence storage, reviewer queue, model/version tracing, and 0–30 provisional/final reporting.
- Benchmark against double-scored expert samples before any high-stakes release; monitor drift, subgroup performance, and reviewer overrides.

### MVP 4 — Exam operations
- Add proctor workflows, accommodations, incident handling, template versioning, psychometric item analytics, security monitoring, backups, and load/penetration testing.

## Next.js examination dashboard boilerplate

Use this as `app/tests/[attemptId]/reading/page.tsx`. In production, hydrate the initial payload from a server component/API, autosave by **question ID** with an idempotency key, and keep correct answers out of the payload.

```tsx
"use client";

import { useEffect, useState } from "react";

const questions = [
  { id: "r1", prompt: "बालकाः कुत्र गच्छन्ति?", choices: ["विद्यालयम्", "उद्यानम्", "आपणम्", "नदीम्"] },
  { id: "r2", prompt: "वृक्षाः किं ददति?", choices: ["जलम्", "छायां फलानि च", "गृहाणि", "पुस्तकानि"] },
];

export default function ReadingExam() {
  const [seconds, setSeconds] = useState(20 * 60);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const saveAnswer = async (questionId: string, choice: string) => {
    setAnswers((current) => ({ ...current, [questionId]: choice }));
    await fetch("/api/attempts/demo/answers", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ questionId, selectedChoiceKey: choice }),
    });
  };

  return (
    <main className="min-h-screen bg-slate-50 p-4 text-slate-900 md:p-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white p-5 shadow-sm">
        <div><p className="font-semibold">SLPT • Reading / पठनम्</p><p className="text-sm text-slate-500">Intermediate practice assessment</p></div>
        <div className="rounded-lg bg-amber-50 px-4 py-2 font-mono text-lg text-amber-900" aria-live="polite">
          {String(Math.floor(seconds / 60)).padStart(2, "0")}:{String(seconds % 60).padStart(2, "0")}
        </div>
      </header>
      <section className="grid gap-6 lg:grid-cols-2">
        <article className="rounded-2xl bg-white p-6 shadow-sm">
          <h1 className="mb-4 text-xl font-bold">अनुच्छेदः / Passage</h1>
          <p className="font-devanagari text-xl leading-10">ग्रामस्य समीपे एकः विशालः उद्यानः अस्ति। प्रतिदिनं बालकाः तत्र क्रीडितुं गच्छन्ति। उद्याने बहवः वृक्षाः सन्ति, ते छायां फलानि च ददति।</p>
          <p className="mt-5 border-t pt-5 italic text-slate-700">Grāmasya samīpe ekaḥ viśālaḥ udyānaḥ asti. Pratidinaṁ bālakāḥ tatra krīḍituṁ gacchanti.</p>
        </article>
        <form className="space-y-5 rounded-2xl bg-white p-6 shadow-sm">
          <h2 className="text-xl font-bold">Questions / प्रश्नाः</h2>
          {questions.map((question, index) => <fieldset key={question.id} className="border-b pb-5 last:border-0">
            <legend className="mb-3 font-medium">{index + 1}. {question.prompt}</legend>
            {question.choices.map((choice) => <label key={choice} className="mb-2 flex cursor-pointer gap-3 rounded-lg p-2 hover:bg-indigo-50">
              <input type="radio" name={question.id} checked={answers[question.id] === choice} onChange={() => saveAnswer(question.id, choice)} />{choice}
            </label>)}
          </fieldset>)}
          <button type="button" className="rounded-lg bg-indigo-600 px-5 py-3 font-semibold text-white">Save & continue</button>
        </form>
      </section>
    </main>
  );
}
```
