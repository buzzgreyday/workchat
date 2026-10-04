/**
 * Solving the guest trial's proof-of-work.
 *
 * The backend hands out `challenge = sha256(salt + n)` for a secret `n` no
 * larger than `maxnumber`; finding `n` means trying them in turn. Well under a
 * second for one person, and a real cost to a script asking for thousands of
 * trials, which is the whole point. The shape is ALTCHA's (altcha.org); the
 * backend's half is `backend/app/services/trial/pow.py`.
 *
 * Off the main thread where it can be, so the page does not stutter while it
 * runs: a Web Worker built from a Blob, because a worker script must be
 * same-origin with the page and the embed is served from the chat's origin,
 * not the host's. If the host's CSP refuses blob: workers, or the worker
 * breaks, the same search runs on the main thread in short slices instead.
 *
 * Needs `crypto.subtle`, which browsers only give a secure context — https, or
 * localhost. Over plain http on a LAN address the solve fails and the chat
 * says so.
 */

export interface Challenge {
  algorithm: string;
  challenge: string;
  maxnumber: number;
  salt: string;
  signature: string;
}

/**
 * Find the number. Self-contained on purpose — it is also the worker's
 * source, via `toString()`, so it may use nothing but browser globals.
 * Hashes in batches, since each digest is a promise and awaiting them one at a
 * time spends most of its time waiting rather than hashing.
 */
async function search(
  salt: string,
  challenge: string,
  maxnumber: number,
): Promise<number> {
  const encoder = new TextEncoder();
  const batch = 256;

  for (let start = 0; start <= maxnumber; start += batch) {
    const numbers: number[] = [];

    for (
      let n = start;
      n < start + batch && n <= maxnumber;
      n++
    ) {
      numbers.push(n);
    }

    const digests = await Promise.all(
      numbers.map((n) =>
        crypto.subtle.digest(
          "SHA-256",
          encoder.encode(salt + n),
        ),
      ),
    );

    const found = digests.findIndex(
      (digest) =>
        Array.from(new Uint8Array(digest), (byte) =>
          byte.toString(16).padStart(2, "0"),
        ).join("") === challenge,
    );

    if (found >= 0) {
      return start + found;
    }
  }

  return -1;
}

function inWorker(
  challenge: Challenge,
): Promise<number> {
  return new Promise((resolve, reject) => {
    const source =
      `const search = ${search.toString()};\n` +
      `self.onmessage = async (event) => {\n` +
      `  const { salt, challenge, maxnumber } = event.data;\n` +
      `  self.postMessage(await search(salt, challenge, maxnumber));\n` +
      `};\n`;

    const url = URL.createObjectURL(
      new Blob([source], {
        type: "text/javascript",
      }),
    );

    let worker: Worker;

    try {
      worker = new Worker(url);
    } catch (error) {
      URL.revokeObjectURL(url);
      reject(error);
      return;
    }

    const done = () => {
      worker.terminate();
      URL.revokeObjectURL(url);
    };

    worker.onmessage = (event: MessageEvent<number>) => {
      done();
      resolve(event.data);
    };

    worker.onerror = (event) => {
      done();
      reject(new Error(event.message || "worker failed"));
    };

    worker.postMessage({
      salt: challenge.salt,
      challenge: challenge.challenge,
      maxnumber: challenge.maxnumber,
    });
  });
}

/**
 * The solution, packed as the backend reads it: base64 of the challenge as
 * given plus the number found.
 */
export async function solve(
  challenge: Challenge,
): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error(
      "No crypto.subtle — not a secure context",
    );
  }

  let number: number;

  try {
    number = await inWorker(challenge);
  } catch {
    number = await search(
      challenge.salt,
      challenge.challenge,
      challenge.maxnumber,
    );
  }

  if (number < 0) {
    throw new Error("Challenge has no solution");
  }

  return btoa(
    JSON.stringify({ ...challenge, number }),
  );
}
