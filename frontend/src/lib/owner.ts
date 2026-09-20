/**
 * Whose CV this is.
 *
 * Server-only, and deliberately not `NEXT_PUBLIC_`. A public variable is
 * inlined into the browser bundle when `next build` runs, which would mean a
 * new name needs a new image; read on the server during dynamic rendering, the
 * same image serves any owner and a restart is enough to change one.
 *
 * Never import this from a `"use client"` module. Passing the result down as a
 * prop is fine — that crosses the boundary; an import would drag the module
 * into the bundle and put the build-time baking back.
 */

export interface Owner {
  name: string;
  githubUrl: string;
  linkedinUrl: string;
}

/**
 * Unset and empty are different answers.
 *
 * Unset means "nothing was said", so the default stands. Empty means "I do not
 * have one" — an owner with no LinkedIn must get no LinkedIn link, not the
 * author's. Testing truthiness would collapse the two and quietly point a
 * stranger's header at someone else's profile.
 */
function configured(
  value: string | undefined,
  fallback: string,
): string {
  return value === undefined ? fallback : value;
}

export function readOwner(): Owner {
  return {
    name: configured(
      process.env.OWNER_NAME,
      "Michael",
    ),
    githubUrl: configured(
      process.env.OWNER_GITHUB_URL,
      "https://github.com/buzzgreyday",
    ),
    linkedinUrl: configured(
      process.env.OWNER_LINKEDIN_URL,
      "https://linkedin.com/in/michael-ringdal",
    ),
  };
}
