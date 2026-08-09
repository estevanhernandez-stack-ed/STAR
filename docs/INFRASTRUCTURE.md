# STAR infrastructure

Provisioned 2026-08-09. Everything below is live and verified, not aspirational.

## Google Cloud project

| | |
| --- | --- |
| Project ID | `star-research-dept` |
| Project number | `390753828501` |
| Firebase console | https://console.firebase.google.com/project/star-research-dept |

A dedicated project, deliberately. STAR is a publicly-deployed hackathon entry;
putting its Firestore, its anonymous-auth users, and its public Cloud Run
traffic inside `project-626labs` would share a blast radius and a quota with
the 626 dashboard. Teardown after 2026-09-07 is one project deletion.

## Billing — read this before adding another project

Linked to billing account `01CBAA-C1C50E-FB7E78`.

**Not** the usual `01A07D-181DC7-0B4BA0`. That account sits at Google's cap of
5 linked projects, and the first link attempt failed with
`Cloud billing quota exceeded`. `01CBAA` had zero projects linked. If a future
project fails to link billing, that cap is why — check
`gcloud billing projects list --billing-account=<id>` before assuming a
permissions problem.

## Services enabled

- `firestore.googleapis.com` — Native mode database, location `nam5`
- `identitytoolkit.googleapis.com` — Firebase Auth, anonymous provider enabled
- `firebase.googleapis.com`, `firebaserules.googleapis.com`

Cloud Run and Artifact Registry are **not** yet enabled; that belongs to the
deploy task.

## What needed billing and what did not

Worth recording, because the two behave differently and it cost a detour:

- **Firestore Native created fine with no billing.** The free tier covers it.
- **Firebase Auth did not.** `identityPlatform:initializeAuth` returns
  `BILLING_NOT_ENABLED`, and until it is initialized, anonymous sign-in fails
  with `CONFIGURATION_NOT_FOUND` — a confusing error that looks like a
  misconfigured client rather than an uninitialized project.

## Gemini is independent of all of this

`GOOGLE_GENAI_USE_VERTEXAI=FALSE`, so Gemini runs through AI Studio on
`GOOGLE_API_KEY` and does not touch this project. Changing cloud projects does
not disturb the working model path.

## Verified end to end

Anonymous sign-in returns a real uid with `sign_in_provider: anonymous`,
token audience `star-research-dept`, issuer
`https://securetoken.google.com/star-research-dept`.

## The web API key is not a secret

`FIREBASE_API_KEY` identifies the project to the browser and is designed to
ship in client code. Security comes from Auth and Firestore rules, not from
hiding it. Do not treat it like `GOOGLE_API_KEY` or `PARALLEL_API_KEY`, which
are secrets and stay in the gitignored `.env`.
