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
import * as SQLite from 'expo-sqlite';
import { MaterialCommunityIcons, MaterialIcons } from '@expo/vector-icons';
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

type QueueStatus = 'queued' | 'pending_sms_fallback' | 'failed';

type SosQueueRow = {
  id?: number;
  eventId: string;
  createdAt: string;
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  tags: EmergencyTagId[];
  customIssue: string | null;
  status: QueueStatus;
};

const COLORS = {
  background: '#121414',
  surface: '#121414',
  surfaceContainerLow: '#1a1c1c',
  surfaceContainer: '#1e2020',
  surfaceContainerHigh: '#282a2b',
  surfaceContainerHighest: '#333535',
  primary: '#ffb3b3',
  primaryContainer: '#ff525f',
  onPrimaryContainer: '#5b0011',
  secondaryContainer: '#05e777',
  secondaryFixedDim: '#00e475',
  onSecondaryContainer: '#00622e',
  outlineVariant: '#5e3f3e',
  onBackground: '#e2e2e2',
  onSurface: '#e2e2e2',
  onSurfaceVariant: '#e8bcbb',
  error: '#ffb4ab',
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
  { label: 'Maps', icon: 'map-outline' },
  { label: 'Guide', icon: 'book-open-variant' },
] as const;

const DB_NAME = 'resq_offline_queue.db';
const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

let databasePromise: Promise<SQLite.SQLiteDatabase> | null = null;

async function getDatabase(): Promise<SQLite.SQLiteDatabase> {
  if (!databasePromise) {
    databasePromise = SQLite.openDatabaseAsync(DB_NAME);
  }

  const db = await databasePromise;
  await db.execAsync(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS sos_queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL,
      latitude REAL,
      longitude REAL,
      accuracy REAL,
      tags_json TEXT NOT NULL,
      custom_issue TEXT,
      status TEXT NOT NULL,
      retry_count INTEGER NOT NULL DEFAULT 0,
      synced_at TEXT
    );
  `);

  return db;
}

async function queueSosPayload(payload: SosQueueRow): Promise<number> {
  const db = await getDatabase();
  const result = await db.runAsync(
    `INSERT INTO sos_queue (
      event_id,
      created_at,
      latitude,
      longitude,
      accuracy,
      tags_json,
      custom_issue,
      status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      payload.eventId,
      payload.createdAt,
      payload.latitude,
      payload.longitude,
      payload.accuracy,
      JSON.stringify(payload.tags),
      payload.customIssue,
      payload.status,
    ],
  );
  return Number(result.lastInsertRowId);
}

function createEventId(): string {
  return `sos_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

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
    borderColor: withTiming(selected ? COLORS.primary : 'rgba(94, 63, 62, 0.42)', {
      duration: 180,
    }),
    backgroundColor: withTiming(
      selected ? 'rgba(255, 82, 95, 0.2)' : 'rgba(40, 42, 43, 0.42)',
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

export default function HomeScreen() {
  const [activeTab, setActiveTab] = useState('Home');
  const [selectedTags, setSelectedTags] = useState<EmergencyTagId[]>([]);
  const [customIssue, setCustomIssue] = useState('');
  const [queueCount, setQueueCount] = useState(0);
  const [statusMessage, setStatusMessage] = useState('Offline queue ready');
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const pulse = useSharedValue(0);
  const sosScale = useSharedValue(1);
  const statusOpacity = useSharedValue(0.72);

  const selectedTagSet = useMemo(() => new Set(selectedTags), [selectedTags]);

  useEffect(() => {
    pulse.value = withRepeat(withTiming(1, { duration: 2000 }), -1, false);
    statusOpacity.value = withRepeat(withSequence(withTiming(1, { duration: 900 }), withTiming(0.72, { duration: 900 })), -1, true);

    getDatabase()
      .then((db) =>
        db.getAllAsync<{ count: number }>(
          "SELECT COUNT(*) AS count FROM sos_queue WHERE status IN ('queued', 'pending_sms_fallback')",
        ),
      )
      .then((rows) => {
        setQueueCount(rows[0]?.count ?? 0);
      })
      .catch(() => {
        setStatusMessage('Queue setup needs attention');
      });
  }, [pulse, statusOpacity]);

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

  const handleSosPress = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setStatusMessage('Capturing GPS signal');
    sosScale.value = withSequence(withSpring(0.94), withSpring(1));
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);

    let latitude: number | null = null;
    let longitude: number | null = null;
    let accuracy: number | null = null;
    let status: QueueStatus = 'queued';

    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status === Location.PermissionStatus.GRANTED) {
        const location = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
        latitude = location.coords.latitude;
        longitude = location.coords.longitude;
        accuracy = location.coords.accuracy;
      } else {
        status = 'pending_sms_fallback';
        setStatusMessage('Location denied. Queuing SOS without GPS');
      }
    } catch {
      status = 'pending_sms_fallback';
      setStatusMessage('GPS unavailable. Queuing SOS fallback');
    }

    try {
      const insertedId = await queueSosPayload({
        eventId: createEventId(),
        createdAt: new Date().toISOString(),
        latitude,
        longitude,
        accuracy,
        tags: selectedTags,
        customIssue: customIssue.trim() || null,
        status,
      });

      setQueueCount((count) => count + 1);
      setStatusMessage(
        latitude && longitude
          ? `SOS queued locally #${insertedId}`
          : `SOS queued for fallback #${insertedId}`,
      );
      setCustomIssue('');
    } catch {
      setStatusMessage('SOS queue failed. Try again now');
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderContent = () => {
    if (activeTab === 'Maps') {
      return (
        <View style={styles.placeholderContainer}>
          <Text style={styles.placeholderText}>Map View Coming Soon</Text>
        </View>
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
              colors={['#ff7a84', COLORS.primaryContainer]}
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
          <Text style={styles.queueText}>{queueCount} local SOS payloads pending sync</Text>
        </Animated.View>

        <Animated.View entering={FadeInUp.delay(150).duration(420)} style={styles.specSection}>
          <Text style={styles.sectionTitle}>
            Specify Emergency <Text style={styles.sectionTitleOptional}>(Optional)</Text>
          </Text>

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
              placeholderTextColor="rgba(232, 188, 187, 0.68)"
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
    borderColor: 'rgba(255, 82, 95, 0.46)',
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
    borderColor: 'rgba(94, 63, 62, 0.34)',
    backgroundColor: 'rgba(40, 42, 43, 0.42)',
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
    backgroundColor: 'rgba(255, 179, 179, 0.08)',
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
    borderColor: 'rgba(94, 63, 62, 0.38)',
    backgroundColor: 'rgba(40, 42, 43, 0.42)',
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