/**
 * PhaseIndicator component for commit #83.
 * 
 * Replaces SessionStepper with 4 phase dots with labels:
 * - Orient (hear the target)
 * - Isolate (understand and break down)
 * - Apply (play with a responsive band)
 * - Reflect (honest specific feedback)
 */

import { View, Text } from 'react-native'
import type { SessionPhase } from '@/src/constants/sessionPhases'
import { SESSION_PHASES, getPhaseIndex } from '@/src/constants/sessionPhases'
import { useSessionPhaseStore } from '@/src/stores/sessionPhaseStore'

export interface PhaseIndicatorProps {
  /** Current phase (optional, defaults to store value) */
  currentPhase?: SessionPhase | null
  /** Whether to show labels (default: true) */
  showLabels?: boolean
}

export function PhaseIndicator({ currentPhase: propPhase, showLabels = true }: PhaseIndicatorProps) {
  const storePhase = useSessionPhaseStore((s) => s.currentPhase)
  const phaseCompletion = useSessionPhaseStore((s) => s.phaseCompletion)
  
  // Use prop if provided, otherwise use store value
  const currentPhase = propPhase !== undefined ? propPhase : storePhase
  
  if (!currentPhase) {
    return null
  }
  
  const currentIndex = getPhaseIndex(currentPhase)
  
  return (
    <View className="flex-row items-center justify-center gap-4 py-3">
      {SESSION_PHASES.map((phase, index) => {
        const isCurrent = index === currentIndex
        const isCompleted = index < currentIndex
        const isPending = index > currentIndex
        
        const phaseLabel = phase.charAt(0).toUpperCase() + phase.slice(1)
        
        return (
          <View key={phase} className="flex-col items-center gap-1">
            {/* Phase dot */}
            <View
              className={`h-3 w-3 rounded-full ${
                isCurrent
                  ? 'bg-amber-accent'
                  : isCompleted
                  ? 'bg-wood-600'
                  : 'bg-wood-300'
              }`}
            />
            
            {/* Phase label */}
            {showLabels && (
              <Text
                className={`font-sans text-xs ${
                  isCurrent
                    ? 'font-semibold text-amber-accent'
                    : isCompleted
                    ? 'text-wood-600'
                    : 'text-wood-300'
                }`}
              >
                {phaseLabel}
              </Text>
            )}
          </View>
        )
      })}
    </View>
  )
}
