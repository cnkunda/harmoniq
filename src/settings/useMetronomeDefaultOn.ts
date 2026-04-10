import { useFocusEffect } from '@react-navigation/native'
import { useCallback, useState } from 'react'

import { getAppPref } from '@/src/db/client'
import { PREF_METRONOME_DEFAULT_ON } from '@/src/db/schema'

/** Reads persisted default; default on when pref unset (`!== '0'`). */
export function useMetronomeDefaultOn(): boolean {
  const [on, setOn] = useState(true)
  useFocusEffect(
    useCallback(() => {
      void getAppPref(PREF_METRONOME_DEFAULT_ON).then((v) => setOn(v !== '0'))
    }, []),
  )
  return on
}
