import {
  UserAgent,
  UserAgentOptions,
  Registerer,
  Inviter,
  SessionState,
  Invitation,
  Session,
  RegistererState,
} from 'sip.js'

export interface SipClientOptions {
  server: string // e.g., 'wss://example.com:7443'
  aor: string // e.g., 'sip:1001@example.com'
  password?: string
  displayName?: string
}

export interface CallEvents {
  onRegister?: (registered: boolean) => void
  onIncomingCall?: (caller: string, callerName: string) => void
  onCallAnswered?: () => void
  onCallTerminated?: () => void
  onCallFailed?: (reason: string) => void
  onMediaStateChange?: (hasMedia: boolean) => void
}

export class SipClient {
  private userAgent: UserAgent | null = null
  private registerer: Registerer | null = null
  private currentSession: Session | null = null
  private remoteAudioElement: HTMLVideoElement | HTMLAudioElement | null = null

  constructor(
    private options: SipClientOptions,
    private events: CallEvents
  ) {}

  public async connect(): Promise<void> {
    const uri = UserAgent.makeURI(this.options.aor)
    if (!uri) throw new Error('Invalid AOR URI')

    const uaOptions: UserAgentOptions = {
      uri,
      transportOptions: {
        server: this.options.server,
      },
      authorizationPassword: this.options.password,
      authorizationUsername: this.options.aor.split('@')[0].replace('sip:', ''),
      displayName: this.options.displayName,
      sessionDescriptionHandlerFactoryOptions: {
        peerConnectionOptions: {
          rtcConfiguration: {
            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
          },
        },
      },
    }

    this.userAgent = new UserAgent(uaOptions)

    // Handle incoming calls
    this.userAgent.delegate = {
      onInvite: (invitation: Invitation) => {
        if (this.currentSession) {
          // Busy
          invitation.reject()
          return
        }
        this.currentSession = invitation
        this.setupSessionDelegates(invitation)
        const caller = invitation.remoteIdentity.uri.user
        const name = invitation.remoteIdentity.displayName || caller
        if (this.events.onIncomingCall) {
          this.events.onIncomingCall(caller, name)
        }
      },
    }

    await this.userAgent.start()

    // Setup registerer
    this.registerer = new Registerer(this.userAgent)
    this.registerer.stateChange.addListener((newState: RegistererState) => {
      const isRegistered = newState === RegistererState.Registered
      if (this.events.onRegister) {
        this.events.onRegister(isRegistered)
      }
    })

    await this.registerer.register()
  }

  public async disconnect(): Promise<void> {
    if (this.currentSession) {
      await this.terminate()
    }
    if (this.registerer) {
      await this.registerer.unregister()
    }
    if (this.userAgent) {
      await this.userAgent.stop()
    }
    this.userAgent = null
    this.registerer = null
    this.currentSession = null
  }

  public async call(targetURI: string): Promise<void> {
    if (!this.userAgent) throw new Error('SipClient not connected')
    if (this.currentSession) throw new Error('Already in a call')

    let target = targetURI
    if (!target.startsWith('sip:')) {
      const domain = this.options.aor.split('@')[1]
      target = `sip:${target}@${domain}`
    }

    const uri = UserAgent.makeURI(target)
    if (!uri) throw new Error('Invalid target URI')

    const inviter = new Inviter(this.userAgent, uri, {
      sessionDescriptionHandlerOptions: {
        constraints: { audio: true, video: false },
      },
    })

    this.currentSession = inviter
    this.setupSessionDelegates(inviter)

    await inviter.invite()
  }

  public async answer(): Promise<void> {
    if (!this.currentSession || !(this.currentSession instanceof Invitation)) {
      throw new Error('No incoming call to answer')
    }
    await this.currentSession.accept({
      sessionDescriptionHandlerOptions: {
        constraints: { audio: true, video: false },
      },
    })
  }

  public async extendOrHold(_hold: boolean): Promise<void> {
      // not implemented for simplicity
  }

  public async terminate(): Promise<void> {
    if (!this.currentSession) return

    switch (this.currentSession.state) {
      case SessionState.Initial:
      case SessionState.Establishing:
        if (this.currentSession instanceof Inviter) {
          await this.currentSession.cancel()
        } else if (this.currentSession instanceof Invitation) {
          await this.currentSession.reject()
        }
        break
      case SessionState.Established:
        await this.currentSession.bye()
        break
      default:
        break
    }
    this.currentSession = null
  }

  public setMediaElements(remoteAudio: HTMLAudioElement) {
    this.remoteAudioElement = remoteAudio
  }

  private setupSessionDelegates(session: Session) {
    session.stateChange.addListener((newState: SessionState) => {
      switch (newState) {
        case SessionState.Established:
          this.setupRemoteMedia(session)
          if (this.events.onCallAnswered) this.events.onCallAnswered()
          break
        case SessionState.Terminated:
          this.currentSession = null
          if (this.events.onCallTerminated) this.events.onCallTerminated()
          break
      }
    })
  }

  private setupRemoteMedia(session: Session) {
    const sdh = session.sessionDescriptionHandler as any
    if (!sdh || !sdh.peerConnection) return

    const peerConnection = sdh.peerConnection
    const remoteStream = new MediaStream()

    peerConnection.getReceivers().forEach((receiver: any) => {
      if (receiver.track) {
        remoteStream.addTrack(receiver.track)
      }
    })

    if (this.remoteAudioElement) {
      this.remoteAudioElement.srcObject = remoteStream
      this.remoteAudioElement.play().catch((e) => console.error('Audio play failed', e))
    }
    
    if (this.events.onMediaStateChange) {
      this.events.onMediaStateChange(true)
    }
  }
}
