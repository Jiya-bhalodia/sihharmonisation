export function displayDatasetName(name: string) {
  return name.replace(/^\[([^\]]+)\]\s*/, (label, value: string) =>
    /synthetic/i.test(value) && /illustrative/i.test(value) ? '' : label
  )
}
