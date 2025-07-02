# detect_ps_front_service.py

import rclpy
from rclpy.node import Node
import numpy as np
import json

from sensor_msgs.msg import CameraInfo
from geometry_msgs.msg import PointStamped, PoseStamped
from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import String

import tf2_ros
import tf2_geometry_msgs
from tf2_ros import TransformException

from std_srvs.srv import Trigger

class YOLOTFServiceNode(Node):
    def __init__(self):
        super().__init__('yolo_tf_service_node')

        self.K = None
        self.latest_objects = []
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        self.create_subscription(CameraInfo, '/robot3/oakd/stereo/camera_info', self.camera_info_callback, 10)
        self.create_subscription(String, '/detect/object_info', self.object_info_callback, 10)

        self.marker_pub = self.create_publisher(MarkerArray, '/object_markers', 10)
        self.pose_pub = self.create_publisher(PoseStamped, '/detect/object_map_pose', 10)

        self.srv = self.create_service(Trigger, '/detect/object_map_pose_trigger', self.handle_pose_request)

        self.marker_id = 0

    def camera_info_callback(self, msg):
        if self.K is None:
            self.K = np.array(msg.k).reshape(3, 3)
            self.get_logger().info("CameraInfo 수신 완료")

    def object_info_callback(self, msg):
        if self.K is None:
            self.get_logger().warn("CameraInfo 미수신. 변환 불가.")
            return

        try:
            self.latest_objects = json.loads(msg.data)
            self.get_logger().info(f"객체 정보 {len(self.latest_objects)}개 저장")
        except Exception as e:
            self.get_logger().error(f"객체 정보 파싱 실패: {e}")

    def handle_pose_request(self, request, response):
        if self.K is None:
            response.success = False
            response.message = "CameraInfo 없음"
            return response

        if not self.latest_objects:
            response.success = False
            response.message = "객체 정보 없음"
            return response

        obj = self.latest_objects[0]  # 예: 첫 번째 객체만 사용
        try:
            u = obj['center_x']
            v = obj['center_y']
            depth = obj['distance']
            frame_id = obj['frame_id']

            x, y, z = self.pixel_to_3d(u, v, depth)

            point_camera = PointStamped()
            point_camera.header.frame_id = frame_id
            point_camera.point.x = x
            point_camera.point.y = y
            point_camera.point.z = z

            tf1 = self.tf_buffer.lookup_transform(
                'base_link',
                frame_id,
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=1.0)
            )
            point_base = tf2_geometry_msgs.do_transform_point(point_camera, tf1)

            point_offset = PointStamped()
            point_offset.header.frame_id = 'base_link'
            point_offset.point.x = point_base.point.x - 0.5
            point_offset.point.y = point_base.point.y
            point_offset.point.z = point_base.point.z

            tf2 = self.tf_buffer.lookup_transform(
                'map',
                'base_link',
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=1.0)
            )
            point_map = tf2_geometry_msgs.do_transform_point(point_offset, tf2)

            pose_msg = PoseStamped()
            pose_msg.header.frame_id = 'map'
            pose_msg.header.stamp = self.get_clock().now().to_msg()
            pose_msg.pose.position = point_map.point
            pose_msg.pose.orientation.w = 1.0

            self.pose_pub.publish(pose_msg)
            self.get_logger().info(f"PoseStamped 발행 완료: {pose_msg}")

            # Marker도 같이 발행
            marker = Marker()
            marker.header.frame_id = 'map'
            marker.header.stamp = self.get_clock().now().to_msg()
            marker.ns = "objects"
            marker.id = self.marker_id
            self.marker_id += 1
            marker.type = Marker.SPHERE
            marker.action = Marker.ADD
            marker.pose.position = point_map.point
            marker.pose.orientation.w = 1.0
            marker.scale.x = 0.2
            marker.scale.y = 0.2
            marker.scale.z = 0.2
            marker.color.r = 0.0
            marker.color.g = 1.0
            marker.color.b = 0.0
            marker.color.a = 1.0
            marker.lifetime.sec = 1

            marker_array = MarkerArray()
            marker_array.markers.append(marker)
            self.marker_pub.publish(marker_array)

            response.success = True
            response.message = "PoseStamped 발행 완료"

        except Exception as e:
            self.get_logger().error(f"요청 처리 실패: {e}")
            response.success = False
            response.message = f"처리 실패: {e}"

        return response

    def pixel_to_3d(self, u, v, depth):
        fx = self.K[0, 0]
        fy = self.K[1, 1]
        cx = self.K[0, 2]
        cy = self.K[1, 2]

        x = (u - cx) * depth / fx
        y = (v - cy) * depth / fy
        z = depth
        return x, y, z

def main(args=None):
    rclpy.init(args=args)
    node = YOLOTFServiceNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
