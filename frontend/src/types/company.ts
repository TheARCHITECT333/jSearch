export interface Company {
  name: string;
  careers_url: string;
}

export function isValidCompanyUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export interface ParsedCompaniesResult {
  companies: Company[];
  errors: string[];
}

/** Parse + validate a companies JSON file (array of {name, careers_url}). */
export function parseCompaniesJson(text: string): ParsedCompaniesResult {
  const errors: string[] = [];
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (e) {
    return { companies: [], errors: ["File is not valid JSON."] };
  }
  if (!Array.isArray(data)) {
    return { companies: [], errors: ["Expected a JSON array of companies."] };
  }

  const companies: Company[] = [];
  data.forEach((entry, index) => {
    if (typeof entry !== "object" || entry === null) {
      errors.push(`Entry ${index + 1} is not an object.`);
      return;
    }
    const { name, careers_url } = entry as Record<string, unknown>;
    const label =
      typeof name === "string" && name.trim() ? name.trim() : `Entry ${index + 1}`;
    const hasName = typeof name === "string" && Boolean(name.trim());
    const hasUrl =
      typeof careers_url === "string" && isValidCompanyUrl(careers_url.trim());
    if (!hasName) {
      errors.push(`Entry ${index + 1}: "name" is required.`);
    }
    if (!hasUrl) {
      errors.push(
        `${label}: "careers_url" must be a valid HTTP/HTTPS URL.`
      );
    }
    if (!hasName || !hasUrl) return;
    companies.push({ name: name.trim(), careers_url: careers_url.trim() });
  });

  return { companies, errors };
}
