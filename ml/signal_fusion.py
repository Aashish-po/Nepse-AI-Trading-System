# Backward compatibility module - delegates to backend implementation
from backend.app.services.signal_fusion import (
    LSTMSignalProvider as BackendLSTMSignalProvider,
    SignalFusionEngine as BackendSignalFusionEngine,
)

# For backward compatibility, expose the same classes
SignalFusionEngine = BackendSignalFusionEngine
LSTMSignalProvider = BackendLSTMSignalProvider


# Keep the old class names for any direct imports
# Note: The backend version has enhanced functionality including LSTM signal generation
