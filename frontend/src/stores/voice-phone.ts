import { defineStore } from 'pinia'
import { ref } from 'vue'
import { SipClient } from '@/utils/sip-client'

export const useVoicePhoneStore = defineStore('voice-phone', () => {
  const isVisible = ref(false)
  const isRegistered = ref(false)
  const callStatus = ref<'idle' | 'calling' | 'ringing' | 'connected' | 'onhold'>('idle')
  const currentNumber = ref('')
  const currentCallId = ref<string | null>(null)
  const duration = ref(0)
  const isMuted = ref(false)
  
  // SIP Config
  const extension = ref('')
  const password = ref('')
  const wsUrl = ref('')
  const domain = ref('')
  
  let sipClient: SipClient | null = null
  let timerInterval: any = null

  function toggleVisibility() {
    isVisible.value = !isVisible.value
  }

  function setVisible(val: boolean) {
    isVisible.value = val
  }

  async function initSip(serverUrl: string, extString: string, pwd: string, serverDomain: string) {
    wsUrl.value = serverUrl
    extension.value = extString
    password.value = pwd
    domain.value = serverDomain

    if (sipClient) {
      await sipClient.disconnect()
    }

    const aor = `sip:${extString}@${serverDomain}`
    sipClient = new SipClient({
      server: serverUrl,
      aor,
      password: pwd,
      displayName: extString
    }, {
      onRegister: (registered) => {
        isRegistered.value = registered
      },
      onIncomingCall: (caller, name) => {
        currentNumber.value = caller
        callStatus.value = 'ringing'
        isVisible.value = true
      },
      onCallAnswered: () => {
        callStatus.value = 'connected'
        startTimer()
      },
      onCallTerminated: () => {
        callStatus.value = 'idle'
        stopTimer()
      },
      onCallFailed: (reason) => {
        callStatus.value = 'idle'
        stopTimer()
      }
    })

    await sipClient.connect()
  }

  async function startCall(number: string) {
    if (!sipClient) return
    currentNumber.value = number
    callStatus.value = 'calling'
    duration.value = 0
    try {
      await sipClient.call(number)
    } catch (e) {
      callStatus.value = 'idle'
    }
  }

  async function answer() {
    if (!sipClient) return
    await sipClient.answer()
  }

  async function hangup() {
    if (callStatus.value === 'idle') return
    if (sipClient) {
      await sipClient.terminate()
    }
    callStatus.value = 'idle'
    stopTimer()
  }

  function startTimer() {
    duration.value = 0
    if (timerInterval) clearInterval(timerInterval)
    timerInterval = setInterval(() => {
      duration.value++
    }, 1000)
  }

  function stopTimer() {
    if (timerInterval) clearInterval(timerInterval)
    timerInterval = null
  }

  function setRemoteAudio(audioEl: HTMLAudioElement) {
    if (sipClient) {
      sipClient.setMediaElements(audioEl)
    }
  }

  return {
    isVisible,
    isRegistered,
    callStatus,
    currentNumber,
    currentCallId,
    duration,
    isMuted,
    extension,
    password,
    wsUrl,
    domain,
    toggleVisibility,
    setVisible,
    initSip,
    startCall,
    answer,
    hangup,
    setRemoteAudio
  }
})
