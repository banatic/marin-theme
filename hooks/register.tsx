import type { Register, ThemeSetArgs } from 'claude-code'

// Kitagawa Marin stickers strewn over a dark ground of manga screentone dots,
// the chat area frosted over them so its text stays clear.
//
// Claude Desktop (5.11492.5) draws a backdrop from SVG only, and the engine
// scrubs every way a mod could embed a picture in one: <image>, feImage,
// foreignObject, CSS url() and image-set(), data: fonts. A still `image`
// backdrop is accepted by the engine and not drawn by this Desktop build.
// So assets/exact.py turns each picture into vector marks, one per pixel run,
// that paint a display-size master bitmap value for value. The whole backdrop
// tree holds 262,144 characters, so assets/build_many.py sizes eight pictures
// (and gathers their greys into sixteen tones) to fit it together, and writes
// one set of layers per rotation: the pictures trade places over time.

const SCENE = 'marin-gallery'
const ROTATE_MS = 10 * 60 * 1000
const PICS = 'assets/pics'

// Frost and a veil over the pictures, so text over a white sticker stays readable.
const LOOK: ThemeSetArgs = {
  backdrop: { scene: SCENE, glass: { blur: 4, opacity: 0.7 } },
  overrideColorScheme: 'dark',
}

// Module state: starts over on a reload, which is fine for a rotation.
let offset = 0
let manifest: number[] | undefined // layers in each rotation
const files = new Map<string, string>()

function rotationNow(count: number): number {
  const turn = Math.floor(Date.now() / ROTATE_MS) + offset
  return ((turn % count) + count) % count
}

export const register: Register = (on) => {
  // Neither a reload of this mod nor --resume keeps the look, so set it here.
  on('session.start', async ($, e, next) => {
    // Not drawn only means no desktop or mobile client is attached yet: the
    // theme stands and draws when one is, so there is nothing to tell.
    await $.theme.set(LOOK)
    $.ui.status(undefined)

    await $.command.register({ name: 'marin', description: 'Put the Marin look on, or move the pictures round one place' })
    await $.command.register({ name: 'plain', description: 'Take the Marin look off' })
    $.clock.every(ROTATE_MS, () => $.ui.invalidate('ui.render'))
    return next(e)
  })

  // Runs for every mod's backdrop: draw only this mod's scene.
  on('ui.render', { component: 'Backdrop' }, async ($, e, next) => {
    if (e.props.plugin !== $.plugin.name || e.props.scene !== SCENE) return next(e)
    if (e.surface !== 'desktop' && e.surface !== 'mobile') return next(e)
    const { Box, Svg } = $.ui.resolve(e)

    const read = async (name: string) => {
      const hit = files.get(name)
      if (hit !== undefined) return hit
      const text = await $.fs.read(`${$.plugin.root}/${PICS}/${name}`)
      files.set(name, text)
      return text
    }
    manifest ??= JSON.parse(await read('many.json')) as number[]
    const n = rotationNow(manifest.length)
    const names = Array.from({ length: manifest[n]! }, (_, k) => `many-${n}-${k}.svg`)
    const [ground, ...layers] = await Promise.all([read('ground.svg'), ...names.map(read)])

    return Box({
      width: '100%',
      height: '100%',
      overflow: 'hidden',
      children: [
        Svg({ source: ground!, alt: 'A dark ground with manga screentone dots fading in from two corners' }),
        // The stickers' layers stack in paint order, each a plain image.
        ...layers.map((source, k) => Svg({ source, alt: k === 0 ? 'Kitagawa Marin stickers strewn over the window' : 'More of the same stickers' })),
      ],
    })
  })

  on('command.run', { command: 'marin' }, async ($) => {
    offset += 1
    const set = await $.theme.set(LOOK)
    $.ui.invalidate('ui.render')
    return { text: set.isDrawn ? 'Marin look is on ✦ pictures moved round' : `Not drawn: ${set.reason}` }
  })

  on('command.run', { command: 'plain' }, async ($) => {
    const cleared = await $.theme.clear()
    return { text: cleared.isDrawn ? 'the theme stands' : cleared.reason }
  })
}
