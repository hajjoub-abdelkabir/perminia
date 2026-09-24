# Security and responsible demonstration

This release is a **localhost-only technical showcase**, not an internet deployment guide.

- Use fictional data. Do not upload real identity documents, private learner records or real chat transcripts.
- Credentials are randomly generated into ignored `data/showcase/` files. Provider keys are not loaded by the showcase compose file. AI is disabled explicitly.
- Only localhost port 5184 is published. PostgreSQL remains inside the showcase Docker network. Do not change the binding to a public interface to share a demo.
- The application uses authenticated sessions, CSRF/origin checks, school scopes and database policies in the relevant data paths. The runtime DB login is distinct from the migration/seed owner.
- Reading completion is not mastery. Synthetic publication records are software fixtures, not human accreditation of driving-law content.
- Never publish `.env`, `data/`, database dumps, account files or screen recordings containing credentials. Run the public-export check before every release; it catches known signatures and known local credentials, not every possible form of secret.
- Before a real pilot: review curriculum rights/accuracy, enable HTTPS/secure cookies, restrict origins, separate staging, apply retention rules, test restoration outside the machine, add monitoring and monetary AI caps, and review authorization end-to-end.

If you discover a vulnerability, use the repository's private security-reporting channel if enabled, or contact its owner privately. Do not post credentials or real user data in a public issue. No external security audit is claimed.
