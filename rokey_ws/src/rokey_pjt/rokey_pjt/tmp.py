#!/usr/bin/env python3

# navi_test.py

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped, Twist
from nav2_simple_commander.robot_navigator import BasicNavigator
from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator
from tf_transformations import quaternion_from_euler
import time


def create_pose(x, y, yaw_deg, navigator):
    pose = PoseStamped()
    pose.header.frame_id = 'map'
    pose.header.stamp = navigator.get_clock().now().to_msg()
    pose.pose.position.x = x
    pose.pose.position.y = y

    yaw_rad = yaw_deg * 3.141592 / 180.0
    q = quaternion_from_euler(0, 0, yaw_rad)
    pose.pose.orientation.x = q[0]
    pose.pose.orientation.y = q[1]
    pose.pose.orientation.z = q[2]
    pose.pose.orientation.w = q[3]
    return pose


class ParkingLocationCommander(Node):
    def __init__(self):
        super().__init__('parking_location_commander')

        self.navigator = BasicNavigator()
        self.dock_navigator = TurtleBot4Navigator()

        self.location_map = {
            "A-1": (-2.28, -5.01, -90.0),
            "A-2": (-1.32, -5.15, -90.0),
            "B-1": (1.03, -2.06, 0.0),
            "B-2": (0.94, -1.10, 0.0),
            "C-1": (-2.95, -3.54, 180.0),
            "C-2": (-3.04, -4.59, 180.0),
        }

        self.initial_xyyaw = (-0.02, -0.02, 90.0)

        self.go_to_initial_pose()  # ✅ AMCL 초기화 + 실제 이동 포함

        if self.dock_navigator.getDockedStatus():
            self.get_logger().info('🚦 현재 도킹 상태 → 언도킹 수행')
            self.dock_navigator.undock()
            time.sleep(2.0)
        else:
            self.get_logger().info('🚦 현재 도킹 상태가 아님 → 언도킹 건너뜀')

        self.perform_a2_and_rotate()  # ✅ 함수명도 A-2로 맞춤

        self.subscription = self.create_subscription(
            String,
            '/parking/location',
            self.location_callback,
            10
        )
        self.get_logger().info('✅ /parking/location 토픽 구독 시작 (테스트 모드)')
        self.cmd_vel_pub = self.create_publisher(Twist, '/robot3/cmd_vel', 10)

    def perform_a2_and_rotate(self):
        self.get_logger().info("🗺️ A-2 위치로 이동 시작...")
        if "A-2" in self.location_map:
            x, y, yaw = self.location_map["A-2"]
            target_pose = create_pose(x, y, yaw, self.navigator)
            self.go_to_pose_blocking(target_pose, "A-2 주차 위치")

            time.sleep(2.0)
            self.get_logger().info("⏳ 2초 대기 완료.")

            twist_msg = Twist()
            twist_msg.angular.z = 0.5

            duration = 3.141592 / 0.5
            self.get_logger().info(f"↪️ 제자리 180도 회전 시작 (예상 {duration:.2f}초)")

            start_time = self.get_clock().now().seconds_nanoseconds()[0]
            while self.get_clock().now().seconds_nanoseconds()[0] - start_time < duration:
                self.cmd_vel_pub.publish(twist_msg)
                time.sleep(0.1)

            twist_msg.angular.z = 0.0
            self.cmd_vel_pub.publish(twist_msg)
            self.get_logger().info("✅ 180도 회전 완료, 로봇 정지!")
        else:
            self.get_logger().error("❌ A-2 위치가 location_map에 정의되어 있지 않습니다.")

    def go_to_pose_blocking(self, pose, description):
        self.get_logger().info(f"🚗 이동 시작: {description}")
        self.navigator.goToPose(pose)
        start_time = self.navigator.get_clock().now()

        while not self.navigator.isTaskComplete():
            feedback = self.navigator.getFeedback()
            if feedback:
                elapsed = self.navigator.get_clock().now() - start_time
                self.get_logger().info(
                    f"➡️ 진행 중 - 남은 거리: {feedback.distance_remaining:.2f} m, "
                    f"경과 시간: {elapsed.nanoseconds / 1e9:.1f} s"
                )
            time.sleep(0.2)

        result = self.navigator.getResult()
        if result == BasicNavigator.TaskResult.SUCCEEDED:
            self.get_logger().info(f"✅ {description} 이동 완료!")
        else:
            self.get_logger().error(f"❌ {description} 이동 실패: {result}")

    def go_to_initial_pose(self):
        initial = create_pose(*self.initial_xyyaw, self.navigator)
        self.navigator.setInitialPose(initial)
        self.get_logger().info('✅ AMCL 초기 Pose 설정 완료')
        time.sleep(1.0)
        self.navigator.waitUntilNav2Active()
        self.get_logger().info('✅ Nav2 활성화 완료')

        # ✅ 반드시 초기 Pose로 실제 이동 명령
        self.go_to_pose_blocking(initial, "AMCL 초기 위치로 이동")

    def location_callback(self, msg):
        location = msg.data.strip()
        self.get_logger().info(f"📌 Received parking command: {location}")

        if location not in self.location_map:
            self.get_logger().warn(f"❗ Unknown location: {location}")
            return

        x, y, yaw = self.location_map[location]
        target_pose = create_pose(x, y, yaw, self.navigator)
        self.go_to_pose_blocking(target_pose, f"지정 주차 위치: {location}")
        time.sleep(3.0)


def main():
    rclpy.init()
    commander = ParkingLocationCommander()

    try:
        rclpy.spin(commander)
    except KeyboardInterrupt:
        commander.get_logger().info('🛑 종료 요청 감지')
    finally:
        commander.navigator.lifecycleShutdown()
        commander.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
