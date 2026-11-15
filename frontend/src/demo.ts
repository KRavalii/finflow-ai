// Presentation only: the backend independently enforces read-only mode.
export const isDemoMode = () => import.meta.env.VITE_DEMO_MODE === 'true'
