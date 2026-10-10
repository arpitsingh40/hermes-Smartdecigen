# V160 · WEB APPLICATION SECURITY — Andrew Hoffman
Tier 3 · Technology · Tree Memory

## ROOT
The OWASP Top 10 is the minimum; real security requires understanding the full attack surface of web applications. Hoffman provides the comprehensive guide: reconnaissance (how attackers map your system), offense (the actual attacks — XSS, CSRF, SQL injection, SSRF, auth bypass, session hijacking), and defense (secure coding, Content Security Policy, Subresource Integrity, secure headers, input validation). Core principle: never trust the client. Every input from the browser, mobile app, or API can be manipulated.

## TRUNK
Key vulnerabilities: (1) XSS: inject JavaScript into a page that other users see. The most common web vulnerability. Defense: output encoding, CSP headers. (2) CSRF: trick a logged-in user into performing an action. Defense: CSRF tokens, SameSite cookies. (3) SQL Injection: inject SQL through user input. Defense: parameterized queries (never string concatenation). (4) Auth problems: weak password policies, no MFA, session fixation, JWT misconfiguration. Defense: standard auth libraries, MFA, session rotation. (5) SSRF: trick the server into making requests to internal systems. Defense: URL validation, network segmentation. Security is a process, not a feature: threat modeling, penetration testing, bug bounty programs, security reviews in every PR.

## FRUIT
- WHEN building a web app → APPLY input validation: never trust the client. Validate everything server-side.
- WHEN a security incident occurs → APPLY post-mortem + fix-the-class: one bug fixed = every similar bug found and fixed.

## SEEDS
- "Never trust the client. Every input can be manipulated."
- "Parameterized queries prevent SQL injection. Never concatenate user input into SQL."
- "Security is a process, not a feature. Threat model continuously."

## GRAFTS
- → Site Reliability Engineering: the operational layer that detects and responds to security incidents.
- → Designing Data-Intensive Applications: the data layer security.
