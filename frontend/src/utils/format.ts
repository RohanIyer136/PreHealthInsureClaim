export const label = (value: string) =>
  value
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
export function date(value: string): string {
  // Calendar-only source dates must not shift with the reviewer's timezone.
  const parsed = new Date(value.length === 10 ? value + "T12:00:00" : value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
}
