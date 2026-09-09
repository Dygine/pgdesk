let counter = 1000
export const uid = (prefix = 'id') => `${prefix}_${(counter++).toString(36)}${Date.now().toString(36).slice(-4)}`

export function genPassword() {
  const words = ['Sunrise', 'Anchor', 'Harbour', 'Lantern', 'Copper', 'Meadow', 'Falcon', 'Quartz']
  const w = words[Math.floor(Math.random() * words.length)]
  const n = Math.floor(1000 + Math.random() * 9000)
  const s = '!@#$%&*'[Math.floor(Math.random() * 7)]
  return `${w}${n}${s}`
}

export function slugEmailDomain(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '') + '.in'
}
