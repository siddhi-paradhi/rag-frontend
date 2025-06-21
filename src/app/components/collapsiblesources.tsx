'use client'

import { useState } from 'react'
import { BookOpen, ChevronDown, ChevronUp } from 'lucide-react'

export const CollapsibleSources = ({ 
  sources,
  darkMode = false 
}: { 
  sources: string[]
  darkMode?: boolean
}) => {
  const [expanded, setExpanded] = useState(false)

  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-4 pt-4 border-t border-gray-200/20">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 mb-2 w-full text-left"
      >
        {expanded ? (
          <ChevronUp size={14} className={darkMode ? 'text-gray-400' : 'text-gray-500'} />
        ) : (
          <ChevronDown size={14} className={darkMode ? 'text-gray-400' : 'text-gray-500'} />
        )}
        <BookOpen size={14} className={darkMode ? 'text-gray-400' : 'text-gray-500'} />
        <span className={`text-xs font-medium ${
          darkMode ? 'text-gray-400' : 'text-gray-500'
        }`}>
          Sources ({sources.length})
        </span>
      </button>
      
      {expanded && (
        <div className="space-y-1">
          {sources.map((source, i) => (
            <div 
              key={i} 
              className={`text-xs p-2 rounded ${
                darkMode 
                  ? 'bg-gray-800 text-gray-300' 
                  : 'bg-gray-50 text-gray-600'
              }`}
            >
              {source}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}