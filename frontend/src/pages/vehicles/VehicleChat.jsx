import { useCallback } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import AssistantChat from '../../components/chat/AssistantChat'

export default function VehicleChat() {
  const { id } = useParams()
  const navigate = useNavigate()
  const location = useLocation()

  // "True back": return to wherever the user opened the assistant from
  // (e.g. /recommendations). Falls back to in-app history, then to the
  // vehicle overview for deep links / fresh loads with no history.
  const goBack = useCallback(() => {
    const from = location.state?.from
    if (from) {
      navigate(from)
    } else if (window.history.state?.idx > 0) {
      navigate(-1)
    } else {
      navigate(`/vehicles/${id}`)
    }
  }, [location.state, navigate, id])

  return <AssistantChat vehicleId={id} variant="page" onBack={goBack} />
}
