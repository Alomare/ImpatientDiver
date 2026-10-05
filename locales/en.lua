-- Impatient Diver: English texts, the source of every translation.
-- Translators: see TRANSLATING.md in Mod Options Menu's repository (the same files and tool work for this mod).
-- These show in Mod Options Menu (escape menu > MODS), which upper-cases the mod name and the choices, and in Mod
-- Bindings Menu (Options > Controls > MODS).
return {
    mod = 'impatient_diver',
    title = 'Impatient Diver',
    language = 'en',
    strings = {
        -- The mod's name: its category button in Mod Options Menu and its section in Mod Bindings Menu.
        ['option.mod'] = 'Impatient Diver',
        -- Two of the three choices of each skip (the third, OFF, is the game's own word).
        ['option.choice.manual'] = 'Manual',
        ['option.choice.automatic'] = 'Automatic',
        -- The skips: their names, then the text shown beside each.
        ['option.login.label'] = 'Log-in Ship Intro',
        ['option.login.description'] = 'The camera flying into the ship and your Helldiver walking to the bridge after you log in. Manual: press spacebar (or your Mod Bindings Menu key) while it plays. Automatic: skipped as soon as it starts.',
        ['option.pod.label'] = 'Cryo Pod Transition',
        ['option.pod.description'] = 'Your cryo pod rolling in and your Helldiver stepping out when you arrive on a ship. You take control at the pod exit. Manual: press spacebar (or your Mod Bindings Menu key) while it plays. Automatic: skipped as soon as it starts.',
        ['option.ftl.label'] = 'FTL Transition',
        ['option.ftl.description'] = 'The FTL jump when the ship travels to another planet and when you join a lobby. Loading still happens. Manual: press spacebar (or your Mod Bindings Menu key) while it plays. Automatic: skipped as soon as it starts. When joining a lobby, one Manual press also skips the cryo pod after it, unless that is Off.',
        ['option.hellpod.label'] = 'Hellpod to Loadout',
        ['option.hellpod.description'] = 'Experimental. Your Helldiver climbing into the hellpod and the camera moving to the drop location screen. The drop location screen, the loadout and the launch are untouched. Manual: press spacebar (or your Mod Bindings Menu key) while it plays. Automatic: skipped as soon as it starts.',
        -- The key names in Mod Bindings Menu: the skip key, and a key that closes the galactic map at once (Escape
        -- always does).
        ['binding.skip'] = 'Skip cutscene',
        ['binding.map'] = 'Close galactic map',
    },
    -- Mod Options Menu's and Mod Bindings Menu's limits, in characters.
    limits = {['option.mod'] = 40, ['option.choice.manual'] = 48, ['option.choice.automatic'] = 48,
              ['option.login.label'] = 64, ['option.login.description'] = 400, ['option.pod.label'] = 64,
              ['option.pod.description'] = 400, ['option.ftl.label'] = 64, ['option.ftl.description'] = 400,
              ['option.hellpod.label'] = 64, ['option.hellpod.description'] = 400,
              ['binding.skip'] = 64, ['binding.map'] = 64},
}
