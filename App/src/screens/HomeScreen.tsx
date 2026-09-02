import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { BlurView } from 'expo-blur';
import * as Haptics from 'expo-haptics';
import { LinearGradient } from 'expo-linear-gradient';
import * as Location from 'expo-location';
import { MaterialCommunityIcons, MaterialIcons } from '@expo/vector-icons';
import { fetchRescue, postReport, type Rescue } from '../api';
import { DEMO_LOCATION, TRACK_POLL_MS } from '../config';
import { createEventId, enqueue, flush, pendingCount, type SosRow } from '../queue';
import { openSmsComposer } from '../sms';
import Animated, {
  FadeInUp,
  LinearTransition,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

type EmergencyTagId = 'medical' | 'trapped' | 'flood' | 'shelter';

type EmergencyTag = {
  id: EmergencyTagId;
  label: string;
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
};

/**
 * The DISHA palette, shared with the operator dashboard.
 *
 * Ground, lines and text are the same chart navy the control room runs on, so
 * the two halves of the system read as one product rather than as two apps that
 * happen to talk to each other. Source of truth:
 * frontend/src/styles.css and frontend/src/shared/utils/constants.js.
 *
 * What is DELIBERATELY not shared: the dashboard reserves brass for actions an
 * operator cannot take back, and hands every other hue to data. This app has
 * one job and one button, and that button is a panic button -- it stays in the
 * warm severity family, because a frightened person reaching for help should
 * find the colour they expect, not the colour our design system prefers.
 *
 * The Material role names are kept as-is. They are used consistently through
 * the screen, and the light/dark relationships below are unchanged, so this is
 * a re-point of values rather than a re-wiring of the UI.
 */
const COLORS = {
  background: '#0b1620',
  surface: '#0b1620',
  surfaceContainerLow: '#10202c',
  surfaceContainer: '#17303f',
  surfaceContainerHigh: '#1e3d50',
  surfaceContainerHighest: '#264a60',

  // Warm family = the emergency. Light tint, strong fill, dark ink on both.
  primary: '#f6b3a4',
  primaryContainer: '#e2543f',
  onPrimaryContainer: '#3a0d05',

  // Cool family = it is working. Matches STATUS_COLORS.IDLE / --ok.
  secondaryContainer: '#2fa98a',
  secondaryFixedDim: '#4fd1ad',
  onSecondaryContainer: '#07352a',

  outlineVariant: '#22475c',
  onBackground: '#e8edf0',
  onSurface: '#e8edf0',
  onSurfaceVariant: '#7e96a6',
  error: '#f08d84',
};

const SPACING = {
  touchTargetMin: 48,
  stackSm: 8,
  gutter: 16,
  marginMobile: 20,
  stackMd: 24,
  stackLg: 40,
};

const EMERGENCY_TAGS: EmergencyTag[] = [
  { id: 'medical', label: 'Medical', icon: 'medical-bag' },
  { id: 'trapped', label: 'Trapped', icon: 'account-injury' },
  { id: 'flood', label: 'Flood', icon: 'waves' },
  { id: 'shelter', label: 'Shelter', icon: 'home-heart' },
];

const NAV_ITEMS = [
  { label: 'Home', icon: 'cloud-upload' },
  { label: 'Safety', icon: 'shield-alert-outline' },
  { label: 'Guide', icon: 'book-open-variant' },
] as const;

/**
 * Cyclone and flood guidance, following the standard NDMA / IMD advice.
 *
 * Hard-coded on purpose. This screen has to work with no signal, no server and
 * a dead battery on the way -- the one moment somebody needs it is the moment
 * nothing else is reachable. Anything fetched would be blank exactly then.
 */
const SAFETY_DO = [
  'Move to the nearest cyclone shelter as soon as you are told to.',
  'Keep your phone charged, and a torch and spare battery within reach.',
  'Store drinking water in clean covered containers before the storm.',
  'Switch off gas and the mains before you leave the house.',
  'Keep ID and documents in a sealed plastic bag.',
  'Listen to the radio or official alerts, not forwards.',
];

const SAFETY_DONT = [
  'Do not walk or drive through moving water — knee-deep water moves a car.',
  'Do not touch fallen power lines, wet switches or a flooded meter board.',
  'Do not go outside when the wind suddenly stops. That is the eye, and it ends.',
  'Do not drink flood water or eat food that has touched it.',
  'Do not go home until the authorities say the area is safe.',
  'Do not forward rescue rumours — a wrong location wastes a boat.',
];

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

function EmergencyTagCard({
  tag,
  selected,
  onToggle,
}: {
  tag: EmergencyTag;
  selected: boolean;
  onToggle: () => void;
}) {
  const pressed = useSharedValue(0);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: withSpring(pressed.value ? 0.96 : 1, { damping: 14, stiffness: 220 }) }],
    borderColor: withTiming(selected ? COLORS.primary : 'rgba(34, 71, 92, 0.55)', {
      duration: 180,
    }),
    backgroundColor: withTiming(
      selected ? 'rgba(226, 84, 63, 0.22)' : 'rgba(23, 48, 63, 0.5)',
      { duration: 180 },
    ),
  }));

  return (
    <Animated.View
      entering={FadeInUp.duration(360)}
      layout={LinearTransition.springify().damping(18).stiffness(160)}
      style={styles.tagWrapper}
    >
      <AnimatedPressable
        accessibilityRole="checkbox"
        accessibilityState={{ checked: selected }}
        onPress={() => {
          Haptics.selectionAsync();
          onToggle();
        }}
        onPressIn={() => {
          pressed.value = 1;
        }}
        onPressOut={() => {
          pressed.value = 0;
        }}
        style={[styles.tagCard, animatedStyle]}
      >
        <BlurView intensity={30} tint="dark" style={StyleSheet.absoluteFill} />
        <View style={[styles.tagIconShell, selected && styles.tagIconShellSelected]}>
          <MaterialCommunityIcons
            name={tag.icon}
            size={32}
            color={selected ? COLORS.onPrimaryContainer : COLORS.primary}
          />
        </View>
        <Text style={styles.tagLabel}>{tag.label}</Text>
      </AnimatedPressable>
    </Animated.View>
  );
}

/**
 * The round trip, made visible: sent -> heard -> help on the way.
 *
 * A panic button that gives no feedback is indistinguishable from a broken
 * one. Each step only lights up on evidence the SERVER gave us -- the incident
 * code it minted, and the assignment it actually committed -- so this is a
 * report of what happened, never an optimistic guess.
 */
function RescueTracker({
  saved,
  incidentCode,
  rescue,
}: {
  saved: boolean;
  incidentCode: string | null;
  rescue: Rescue | null;
}) {
  if (!saved) return null;

  const steps = [
    {
      done: true,
      title: 'Saved on this phone',
      detail: 'It survives if the signal drops',
    },
    {
      done: Boolean(incidentCode),
      title: incidentCode ? 'Control room has it' : 'Sending to control room',
      detail: incidentCode ?? 'Waiting for a connection',
    },
    {
      done: Boolean(rescue?.unitCode),
      title: rescue?.unitCode ? 'Help is on the way' : 'Waiting for a unit',
      detail: rescue?.unitCode
        ? `${rescue.unitCode}` +
          (rescue.etaMin != null ? ` · about ${Math.round(rescue.etaMin)} min` : '') +
          (rescue.shelterCode ? ` · to ${rescue.shelterCode}` : '')
        : 'The control room is choosing a unit',
    },
  ];

  return (
    <Animated.View entering={FadeInUp.duration(360)} style={styles.tracker}>
      {steps.map((step, index) => (
        <View key={step.title} style={styles.trackerRow}>
          <View style={styles.trackerRail}>
            <View style={[styles.trackerDot, step.done && styles.trackerDotDone]}>
              {step.done && <MaterialIcons name="check" size={14} color={COLORS.onSecondaryContainer} />}
            </View>
            {index < steps.length - 1 && (
              <View style={[styles.trackerLine, step.done && styles.trackerLineDone]} />
            )}
          </View>
          <View style={styles.trackerBody}>
            <Text style={[styles.trackerTitle, step.done && styles.trackerTitleDone]}>
              {step.title}
            </Text>
            <Text style={styles.trackerDetail}>{step.detail}</Text>
          </View>
        </View>
      ))}
    </Animated.View>
  );
}

export default function HomeScreen() {
  const [activeTab, setActiveTab] = useState('Home');
  const [selectedTags, setSelectedTags] = useState<EmergencyTagId[]>([]);
  const [customIssue, setCustomIssue] = useState('');
  const [queueCount, setQueueCount] = useState(0);
  const [statusMessage, setStatusMessage] = useState('Offline queue ready');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [people, setPeople] = useState(1);
  const [lastRow, setLastRow] = useState<SosRow | null>(null);
  const [incidentCode, setIncidentCode] = useState<string | null>(null);
  const [rescue, setRescue] = useState<Rescue | null>(null);
  
  const pulse = useSharedValue(0);
  const sosScale = useSharedValue(1);
  const statusOpacity = useSharedValue(0.72);

  const selectedTagSet = useMemo(() => new Set(selectedTags), [selectedTags]);

  useEffect(() => {
    pulse.value = withRepeat(withTiming(1, { duration: 2000 }), -1, false);
    statusOpacity.value = withRepeat(withSequence(withTiming(1, { duration: 900 }), withTiming(0.72, { duration: 900 })), -1, true);

    // Anything stranded by a previous session goes out now, if there is signal.
    // Safe to run blind: client_ref makes a repeated POST return the same
    // incident instead of dropping a second pin on the map.
    pendingCount()
      .then((count) => {
        setQueueCount(count);
        setStatusMessage(count ? `${count} SOS waiting to send` : 'Ready');
        return count ? flush() : null;
      })
      .then(async (result) => {
        if (!result) return;
        setQueueCount(await pendingCount());
        if (result.sent) setStatusMessage(`Sent ${result.sent} saved SOS`);
        else if (result.needsSms) setStatusMessage(`${result.needsSms} need to go by SMS`);
      })
      .catch(() => {
        setStatusMessage('Ready — no connection');
      });
  }, [pulse, statusOpacity]);

  /**
   * Once the control room has the report, keep asking what it did with it.
   *
   * Stops as soon as a unit is on the way -- there is nothing further to learn
   * from this screen, and a phone in a flood should not burn battery polling.
   */
  useEffect(() => {
    if (!incidentCode) return;
    if (rescue?.unitCode) return;

    let cancelled = false;
    const tick = async () => {
      try {
        const next = await fetchRescue(incidentCode);
        if (!cancelled) setRescue(next);
      } catch {
        /* no signal right now; the next tick tries again */
      }
    };

    tick();
    const timer = setInterval(tick, TRACK_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [incidentCode, rescue?.unitCode]);

  const pulseStyle = useAnimatedStyle(() => ({
    opacity: 0.42 * (1 - pulse.value),
    transform: [{ scale: 0.96 + pulse.value * 0.42 }],
  }));

  const sosButtonStyle = useAnimatedStyle(() => ({
    transform: [{ scale: sosScale.value }],
  }));

  const statusDotStyle = useAnimatedStyle(() => ({
    opacity: statusOpacity.value,
  }));

  const toggleTag = (tagId: EmergencyTagId) => {
    setSelectedTags((current) =>
      current.includes(tagId) ? current.filter((id) => id !== tagId) : [...current, tagId],
    );
  };

  /**
   * Write the SOS down first, then try to deliver it.
   *
   * That order is deliberate. The queue write is the only step that cannot
   * fail for a reason outside this phone, so it happens before the network is
   * touched. Everything after it is best-effort, and nothing is lost if the
   * signal dies halfway.
   */
  const handleSosPress = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setIncidentCode(null);
    setRescue(null);
    setStatusMessage('Getting your location');
    sosScale.value = withSequence(withSpring(0.94), withSpring(1));
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);

    let latitude: number | null = null;
    let longitude: number | null = null;
    let accuracy: number | null = null;

    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status === Location.PermissionStatus.GRANTED) {
        // The cached fix first, because it is instant and needs nothing.
        //
        // A fresh high-accuracy fix normally leans on A-GPS, which is a NETWORK
        // assist. With mobile data off and a roof overhead, a cold fix can take
        // half a minute or never arrive at all -- and that is precisely the
        // situation this whole path exists for. So: take the last known
        // position immediately, then give a fresh one a few seconds to beat it.
        const cached = await Location.getLastKnownPositionAsync({
          maxAge: 10 * 60 * 1000,
        });
        if (cached) {
          latitude = cached.coords.latitude;
          longitude = cached.coords.longitude;
          accuracy = cached.coords.accuracy;
        }

        const fresh = await Promise.race([
          Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
          new Promise<null>((resolve) => setTimeout(() => resolve(null), 8000)),
        ]);
        if (fresh) {
          latitude = fresh.coords.latitude;
          longitude = fresh.coords.longitude;
          accuracy = fresh.coords.accuracy;
        }

        if (latitude == null) {
          setStatusMessage('No GPS fix — send by SMS and say where you are');
        }
      } else {
        setStatusMessage('Location denied — send by SMS and say where you are');
      }
    } catch {
      setStatusMessage('No GPS fix yet');
    }

    // Demo override. Your phone is not in the seeded district, and a real fix
    // would put the pin off the map where no unit can reach it. Announced in
    // the status line rather than swapped in silently.
    if (DEMO_LOCATION) {
      latitude = DEMO_LOCATION.lat;
      longitude = DEMO_LOCATION.lon;
      accuracy = accuracy ?? 12;
      setStatusMessage('Using demo location (Puri district)');
    }

    let row: SosRow;
    try {
      row = await enqueue({
        eventId: createEventId(),
        createdAt: new Date().toISOString(),
        latitude,
        longitude,
        accuracy,
        tags: selectedTags,
        customIssue: customIssue.trim() || null,
        people,
        status: latitude == null ? 'pending_sms_fallback' : 'queued',
      });
    } catch {
      setStatusMessage('Could not save the SOS. Tap again');
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      setIsSubmitting(false);
      return;
    }

    setLastRow(row);
    setQueueCount((count) => count + 1);

    // No position: the server refuses a pin it cannot place, so this one can
    // only travel by SMS, where the victim can type a landmark themselves.
    if (latitude == null || longitude == null) {
      setStatusMessage('Saved. Send by SMS to get help moving');
      setIsSubmitting(false);
      return;
    }

    setStatusMessage('Sending to the control room');
    try {
      const incident = await postReport(row);
      setQueueCount(await pendingCount());
      setIncidentCode(incident.code);
      setStatusMessage(`Control room has it — ${incident.code}`);
      setCustomIssue('');
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {
      setStatusMessage('No connection. Saved — send by SMS instead');
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    } finally {
      setIsSubmitting(false);
    }
  };

  /** Hand the newest SOS to the SMS composer. The victim presses send. */
  const handleSmsFallback = async () => {
    const row = lastRow;
    if (!row) return;
    Haptics.selectionAsync();
    const opened = await openSmsComposer(row);
    setStatusMessage(opened ? 'Press send in your messages app' : 'No SMS app on this phone');
  };

  const renderContent = () => {
    if (activeTab === 'Safety') {
      return (
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
          <Animated.View entering={FadeInUp.duration(360)} style={styles.heroCopy}>
            <Text style={styles.title}>Do's and Don'ts</Text>
            <Text style={styles.subtitle}>
              Works with no signal. Read it before you need it.
            </Text>
          </Animated.View>

          <View style={styles.safetyBlock}>
            <View style={styles.safetyHead}>
              <MaterialCommunityIcons
                name="check-circle-outline"
                size={22}
                color={COLORS.secondaryFixedDim}
              />
              <Text style={[styles.safetyHeadText, { color: COLORS.secondaryFixedDim }]}>
                Do
              </Text>
            </View>
            {SAFETY_DO.map((line) => (
              <View key={line} style={styles.safetyRow}>
                <View style={[styles.safetyBullet, styles.safetyBulletDo]} />
                <Text style={styles.safetyText}>{line}</Text>
              </View>
            ))}
          </View>

          <View style={styles.safetyBlock}>
            <View style={styles.safetyHead}>
              <MaterialCommunityIcons name="close-circle-outline" size={22} color={COLORS.primary} />
              <Text style={[styles.safetyHeadText, { color: COLORS.primary }]}>Don't</Text>
            </View>
            {SAFETY_DONT.map((line) => (
              <View key={line} style={styles.safetyRow}>
                <View style={[styles.safetyBullet, styles.safetyBulletDont]} />
                <Text style={styles.safetyText}>{line}</Text>
              </View>
            ))}
          </View>
        </ScrollView>
      );
    }
    if (activeTab === 'Guide') {
      return (
        <View style={styles.placeholderContainer}>
          <Text style={styles.placeholderText}>Offline Guide Coming Soon</Text>
        </View>
      );
    }
    
    return (
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Animated.View entering={FadeInUp.duration(420)} style={styles.heroCopy}>
          <Text style={styles.title}>Tap for Emergency Help</Text>
          <Text style={styles.subtitle}>Instantly notify authorities and personal contacts.</Text>
        </Animated.View>

        <View style={styles.sosWrap}>
          <Animated.View pointerEvents="none" style={[styles.sosGlow, pulseStyle]} />
          <Animated.View pointerEvents="none" style={[styles.sosHalo, pulseStyle]} />

          <AnimatedPressable
            accessibilityRole="button"
            disabled={isSubmitting}
            onPress={handleSosPress}
            style={[styles.sosTouchable, sosButtonStyle, isSubmitting && styles.sosTouchableBusy]}
          >
            <LinearGradient
              colors={['#f07a52', COLORS.primaryContainer]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.sosButton}
            >
              {isSubmitting ? (
                <ActivityIndicator size="large" color={COLORS.onPrimaryContainer} />
              ) : (
                <Text style={styles.sosText}>SOS</Text>
              )}
            </LinearGradient>
          </AnimatedPressable>
        </View>

        <Animated.View entering={FadeInUp.delay(80).duration(420)} style={styles.statusPanel}>
          <BlurView intensity={34} tint="dark" style={StyleSheet.absoluteFill} />
          <View style={styles.statusLine}>
            <Animated.View style={[styles.statusDot, statusDotStyle]} />
            <Text style={styles.statusText}>{statusMessage}</Text>
          </View>
          <Text style={styles.queueText}>
            {queueCount === 0 ? 'Everything sent' : `${queueCount} waiting to send`}
          </Text>

          <RescueTracker saved={Boolean(lastRow)} incidentCode={incidentCode} rescue={rescue} />

          {/* The SMS path is the whole point of the offline story, so it is a
              visible button, not something that happens silently. Expo cannot
              send an SMS on its own -- this opens the composer, pre-filled,
              and the victim presses send. */}
          {lastRow && (
            <TouchableOpacity
              accessibilityRole="button"
              activeOpacity={0.82}
              onPress={handleSmsFallback}
              style={styles.smsButton}
            >
              <MaterialCommunityIcons name="message-alert" size={20} color={COLORS.onPrimaryContainer} />
              <Text style={styles.smsButtonText}>Send by SMS instead</Text>
            </TouchableOpacity>
          )}
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(150).duration(420)} style={styles.specSection}>
          <Text style={styles.sectionTitle}>
            Specify Emergency <Text style={styles.sectionTitleOptional}>(Optional)</Text>
          </Text>

          {/* Headcount is a quarter of the dispatch priority and decides which
              size of boat is sent, so it is worth one tap to get right. */}
          <View style={styles.peopleRow}>
            <Text style={styles.peopleLabel}>How many people?</Text>
            <View style={styles.peopleStepper}>
              <TouchableOpacity
                accessibilityRole="button"
                accessibilityLabel="One fewer person"
                onPress={() => {
                  Haptics.selectionAsync();
                  setPeople((n) => Math.max(1, n - 1));
                }}
                style={styles.peopleStep}
              >
                <MaterialIcons name="remove" size={22} color={COLORS.onSurface} />
              </TouchableOpacity>
              <Text style={styles.peopleValue}>{people}</Text>
              <TouchableOpacity
                accessibilityRole="button"
                accessibilityLabel="One more person"
                onPress={() => {
                  Haptics.selectionAsync();
                  setPeople((n) => Math.min(99, n + 1));
                }}
                style={styles.peopleStep}
              >
                <MaterialIcons name="add" size={22} color={COLORS.onSurface} />
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.tagGrid}>
            {EMERGENCY_TAGS.map((tag) => (
              <EmergencyTagCard
                key={tag.id}
                tag={tag}
                selected={selectedTagSet.has(tag.id)}
                onToggle={() => toggleTag(tag.id)}
              />
            ))}
          </View>

          <View style={styles.inputShell}>
            <BlurView intensity={28} tint="dark" style={StyleSheet.absoluteFill} />
            <TextInput
              placeholder="Type custom issue here..."
              placeholderTextColor="rgba(126, 150, 166, 0.75)"
              value={customIssue}
              onChangeText={setCustomIssue}
              style={styles.input}
              returnKeyType="done"
            />
            <TouchableOpacity
              activeOpacity={0.82}
              onPress={() => {
                Haptics.selectionAsync();
                setCustomIssue('');
              }}
              style={styles.inputAction}
            >
              <MaterialIcons name={customIssue ? 'close' : 'arrow-upward'} size={22} color={COLORS.onPrimaryContainer} />
            </TouchableOpacity>
          </View>
        </Animated.View>
      </ScrollView>
    );
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.screen}>
      {renderContent()}
      
      <View style={styles.bottomNav}>
        {NAV_ITEMS.map((item) => (
          <TouchableOpacity
            key={item.label}
            activeOpacity={0.82}
            onPress={() => {
              Haptics.selectionAsync();
              setActiveTab(item.label);
            }}
            style={[styles.navItem, activeTab === item.label && styles.navItemActive]}
          >
            <MaterialCommunityIcons
              name={item.icon}
              size={22}
              color={activeTab === item.label ? COLORS.onSecondaryContainer : COLORS.onSurfaceVariant}
            />
            <Text style={[styles.navLabel, activeTab === item.label && styles.navLabelActive]}>{item.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  content: {
    flexGrow: 1,
    alignItems: 'center',
    paddingHorizontal: SPACING.marginMobile,
    paddingTop: 32,
    paddingBottom: 120, // Clears the new taller nav bar
  },
  tracker: {
    marginTop: SPACING.gutter,
    paddingTop: SPACING.gutter,
    borderTopWidth: 1,
    borderTopColor: 'rgba(34, 71, 92, 0.55)',
  },
  trackerRow: {
    flexDirection: 'row',
    gap: 12,
  },
  trackerRail: {
    alignItems: 'center',
    width: 24,
  },
  trackerDot: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: COLORS.outlineVariant,
    alignItems: 'center',
    justifyContent: 'center',
  },
  trackerDotDone: {
    backgroundColor: COLORS.secondaryContainer,
    borderColor: COLORS.secondaryContainer,
  },
  trackerLine: {
    flex: 1,
    width: 2,
    minHeight: 18,
    backgroundColor: COLORS.outlineVariant,
  },
  trackerLineDone: {
    backgroundColor: COLORS.secondaryFixedDim,
  },
  trackerBody: {
    flex: 1,
    paddingBottom: SPACING.gutter,
  },
  trackerTitle: {
    color: COLORS.onSurfaceVariant,
    fontSize: 15,
    fontWeight: '600',
  },
  trackerTitleDone: {
    color: COLORS.onSurface,
  },
  trackerDetail: {
    color: COLORS.onSurfaceVariant,
    fontSize: 13,
    opacity: 0.8,
    marginTop: 2,
  },
  smsButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: SPACING.stackSm,
    marginTop: 14,
    minHeight: SPACING.touchTargetMin,
    borderRadius: 14,
    backgroundColor: COLORS.primary,
  },
  smsButtonText: {
    color: COLORS.onPrimaryContainer,
    fontSize: 15,
    fontWeight: '700',
  },
  peopleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: SPACING.gutter,
  },
  peopleLabel: {
    color: COLORS.onSurfaceVariant,
    fontSize: 15,
  },
  peopleStepper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.gutter,
    paddingHorizontal: SPACING.stackSm,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: COLORS.outlineVariant,
    backgroundColor: 'rgba(23, 48, 63, 0.5)',
  },
  peopleStep: {
    minWidth: SPACING.touchTargetMin,
    minHeight: SPACING.touchTargetMin,
    alignItems: 'center',
    justifyContent: 'center',
  },
  peopleValue: {
    color: COLORS.onSurface,
    fontSize: 18,
    fontWeight: '700',
    minWidth: 26,
    textAlign: 'center',
  },
  safetyBlock: {
    width: '100%',
    marginBottom: SPACING.stackMd,
    padding: SPACING.gutter,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: COLORS.outlineVariant,
    backgroundColor: 'rgba(23, 48, 63, 0.5)',
  },
  safetyHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.stackSm,
    marginBottom: 14,
  },
  safetyHeadText: {
    fontSize: 17,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  safetyRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 12,
  },
  safetyBullet: {
    width: 7,
    height: 7,
    borderRadius: 4,
    marginTop: 8,
  },
  safetyBulletDo: { backgroundColor: COLORS.secondaryFixedDim },
  safetyBulletDont: { backgroundColor: COLORS.primary },
  safetyText: {
    flex: 1,
    color: COLORS.onSurface,
    fontSize: 15.5,
    lineHeight: 22,
  },
  placeholderContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  placeholderText: {
    color: COLORS.onSurfaceVariant,
    fontSize: 18,
    fontWeight: '600',
  },
  heroCopy: {
    width: '100%',
    alignItems: 'center',
    marginBottom: 32,
  },
  title: {
    color: COLORS.onBackground,
    fontSize: 24,
    lineHeight: 32,
    fontWeight: '600',
    textAlign: 'center',
  },
  subtitle: {
    color: COLORS.onSurfaceVariant,
    fontSize: 16,
    lineHeight: 24,
    marginTop: SPACING.stackSm,
    opacity: 0.8,
    textAlign: 'center',
  },
  sosWrap: {
    width: 292,
    height: 292,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: SPACING.stackMd,
  },
  sosGlow: {
    position: 'absolute',
    width: 264,
    height: 264,
    borderRadius: 40,
    backgroundColor: COLORS.primaryContainer,
    shadowColor: COLORS.primaryContainer,
    shadowOpacity: 0.9,
    shadowRadius: 42,
    shadowOffset: { width: 0, height: 0 },
    elevation: 22,
  },
  sosHalo: {
    position: 'absolute',
    width: 264,
    height: 264,
    borderRadius: 40,
    borderWidth: 2,
    borderColor: 'rgba(226, 84, 63, 0.46)',
  },
  sosTouchable: {
    width: 256,
    height: 256,
    borderRadius: 40,
    shadowColor: '#000000',
    shadowOpacity: 0.42,
    shadowRadius: 26,
    shadowOffset: { width: 0, height: 18 },
    elevation: 18,
  },
  sosTouchableBusy: {
    opacity: 0.86,
  },
  sosButton: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 40,
    overflow: 'hidden',
  },
  sosText: {
    color: COLORS.onPrimaryContainer,
    fontSize: 58,
    lineHeight: 64,
    fontWeight: '900',
    textShadowColor: 'rgba(0, 0, 0, 0.3)',
    textShadowOffset: { width: 0, height: 4 },
    textShadowRadius: 12,
  },
  statusPanel: {
    width: '100%',
    maxWidth: 430,
    overflow: 'hidden',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(34, 71, 92, 0.45)',
    backgroundColor: 'rgba(23, 48, 63, 0.5)',
    paddingHorizontal: SPACING.gutter,
    paddingVertical: 14,
    marginBottom: SPACING.stackMd,
  },
  statusLine: {
    minHeight: 22,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: COLORS.secondaryFixedDim,
  },
  statusText: {
    flex: 1,
    color: COLORS.onSurface,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  queueText: {
    color: COLORS.onSurfaceVariant,
    fontSize: 12,
    lineHeight: 16,
    marginTop: 4,
    opacity: 0.78,
  },
  specSection: {
    width: '100%',
    maxWidth: 430,
    gap: SPACING.gutter,
  },
  sectionTitle: {
    color: COLORS.onSurface,
    fontSize: 18,
    lineHeight: 26,
    fontWeight: '600',
    textAlign: 'center',
  },
  sectionTitleOptional: {
    color: COLORS.onSurfaceVariant,
    fontSize: 16,
    fontWeight: '400',
  },
  tagGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    rowGap: SPACING.gutter,
  },
  tagWrapper: {
    width: '48%', 
  },
  tagCard: {
    width: '100%',
    minHeight: 112,
    alignItems: 'center',
    justifyContent: 'center',
    gap: SPACING.stackSm,
    overflow: 'hidden',
    borderRadius: 16,
    borderWidth: 1,
    padding: SPACING.gutter,
  },
  tagIconShell: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 22,
    backgroundColor: 'rgba(246, 179, 164, 0.08)',
  },
  tagIconShellSelected: {
    backgroundColor: COLORS.primary,
  },
  tagLabel: {
    color: COLORS.onSurface,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
    letterSpacing: 0.7,
    textTransform: 'uppercase',
  },
  inputShell: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    overflow: 'hidden',
    borderRadius: 28,
    borderWidth: 1,
    borderColor: 'rgba(34, 71, 92, 0.5)',
    backgroundColor: 'rgba(23, 48, 63, 0.5)',
    paddingLeft: 20,
    paddingRight: 8,
  },
  input: {
    flex: 1,
    minHeight: 56,
    color: COLORS.onSurface,
    fontSize: 16,
    lineHeight: 24,
    paddingVertical: 0,
  },
  inputAction: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 20,
    backgroundColor: COLORS.primaryContainer,
    marginLeft: 10,
  },
  bottomNav: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: 100, 
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingHorizontal: SPACING.gutter,
    paddingBottom: Platform.OS === 'android' ? 24 : 16,
    backgroundColor: COLORS.surface,
    shadowColor: '#000000',
    shadowOpacity: 0.5,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: -4 },
    elevation: 20,
  },
  navItem: {
    width: 64,
    height: 64,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
  },
  navItemActive: {
    borderRadius: 32,
    backgroundColor: COLORS.secondaryContainer,
  },
  navLabel: {
    color: COLORS.onSurfaceVariant,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '700',
    letterSpacing: 0.55,
    marginTop: 3,
  },
  navLabelActive: {
    color: COLORS.onSecondaryContainer,
  },
});