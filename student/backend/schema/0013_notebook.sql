CREATE TABLE learning.review_notebook (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL, membership_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('lesson','question')),
 lesson_revision_id uuid, section_position integer, question_revision_id uuid REFERENCES content.question_revisions,
 reason text NOT NULL CHECK(reason IN ('unclear','hesitated','ask')), note text NOT NULL DEFAULT '' CHECK(length(note)<=600),
 state text NOT NULL DEFAULT 'open' CHECK(state IN ('open','done')), due_on date NOT NULL,
 version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(tenant_id,membership_id) REFERENCES identity.memberships(tenant_id,id),
 FOREIGN KEY(lesson_revision_id,section_position) REFERENCES content.lesson_sections(revision_id,position),
 CHECK((kind='lesson' AND lesson_revision_id IS NOT NULL AND section_position IS NOT NULL AND question_revision_id IS NULL)
 OR (kind='question' AND question_revision_id IS NOT NULL AND lesson_revision_id IS NULL AND section_position IS NULL)),
 UNIQUE(tenant_id,membership_id,id)
);
CREATE UNIQUE INDEX notebook_lesson ON learning.review_notebook(tenant_id,membership_id,lesson_revision_id,section_position) WHERE kind='lesson';
CREATE UNIQUE INDEX notebook_question ON learning.review_notebook(tenant_id,membership_id,question_revision_id) WHERE kind='question';
CREATE INDEX notebook_due ON learning.review_notebook(tenant_id,membership_id,state,due_on);
CREATE TABLE learning.notebook_activity (
 tenant_id uuid NOT NULL,membership_id uuid NOT NULL,entry_id uuid NOT NULL,day date NOT NULL,
 PRIMARY KEY(tenant_id,membership_id,entry_id,day),
 FOREIGN KEY(tenant_id,membership_id,entry_id) REFERENCES learning.review_notebook(tenant_id,membership_id,id)
);
ALTER TABLE learning.review_notebook ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning.review_notebook FORCE ROW LEVEL SECURITY;
CREATE POLICY learner_scope ON learning.review_notebook USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND membership_id=nullif(current_setting('app.membership_id',true),'')::uuid);
ALTER TABLE learning.notebook_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning.notebook_activity FORCE ROW LEVEL SECURITY;
CREATE POLICY learner_scope ON learning.notebook_activity USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid AND membership_id=nullif(current_setting('app.membership_id',true),'')::uuid);
GRANT SELECT,INSERT,UPDATE ON learning.review_notebook TO sya9a_student_runtime;
GRANT SELECT,INSERT ON learning.notebook_activity TO sya9a_student_runtime;
